import os
import logging
import time
from argparse import ArgumentParser

import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from torch.utils.tensorboard import SummaryWriter

import datasets
import utils
from model import CNN
from nni.nas.pytorch.utils import AverageMeter
from nni.retiarii import fixed_arch



parser = ArgumentParser('darts')
parser.add_argument('--models', default=5, type=int)
parser.add_argument('--dataset', default='cifar.python', type=str)
parser.add_argument('--cutout', default=16, type=int)
parser.add_argument('--channels', default=16, type=int)
parser.add_argument('--layers', default=5, type=int)
parser.add_argument('--lr', type=float, default=0.001)
parser.add_argument('--batch-size', default=96, type=int)
parser.add_argument('--early-stop', default=10, type=int)
parser.add_argument('--log-frequency', default=10, type=int)
parser.add_argument('--epochs', default=600, type=int)
parser.add_argument('--aux-weight', default=0.4, type=float)
parser.add_argument('--drop-path-prob', default=0.2, type=float)
parser.add_argument('--workers', default=4)
parser.add_argument('--grad-clip', default=5., type=float)
parser.add_argument('--checkpoints', default='checkpoints', type=str)
parser.add_argument('--device', default='cuda:0', type=str)
args = parser.parse_args()

logger = logging.getLogger('nni')
device = torch.device(args.device if torch.cuda.is_available() else 'cpu')


DATA_DIR = '~/torch-home/'
dataset_train, dataset_valid = datasets.get_dataset(
    os.path.join(DATA_DIR, args.dataset), cutout_length=args.cutout)
train_loader = torch.utils.data.DataLoader(
    dataset_train, batch_size=args.batch_size, shuffle=True, num_workers=args.workers)
valid_loader = torch.utils.data.DataLoader(
    dataset_valid, batch_size=args.batch_size, shuffle=False, num_workers=args.workers)


models, optimizers, writers = [], [], []
for i in range(args.models):
    with fixed_arch(os.path.join(args.checkpoints, 'checkpoint-%d.json' % i)):
        # (32, 3, 16, 10, 5)
        model = CNN(32, 3, args.channels, 10, args.layers, auxiliary=True)
        model.to(device)
        models.append(model)
        optimizer = optim.Adam(model.parameters(), lr=args.lr)
        optimizers.append(optimizer)
        local_time = time.strftime("%Y-%m-%d-%H-%M-%S", time.localtime())
        writer = SummaryWriter('runs/multi-%d-%s' % (i, local_time))
        writers.append(writer)

criterion = nn.CrossEntropyLoss()


def train(config, train_loader, model, optimizer, criterion, epoch, writer):

    cur_step = epoch * len(train_loader)

    top1 = AverageMeter('top1')
    top5 = AverageMeter('top5')
    losses = AverageMeter('losses')

    model.train()

    for step, (x, y) in enumerate(train_loader):
        x, y = x.to(device), y.to(device)
        bs = x.size(0)

        optimizer.zero_grad()
        logits, aux_logits = model(x)
        loss = criterion(logits, y)
        if config.aux_weight > 0.:
            loss += config.aux_weight * criterion(aux_logits, y)
        loss.backward()
        # gradient clipping
        nn.utils.clip_grad_norm_(model.parameters(), config.grad_clip)
        optimizer.step()

        accuracy = utils.accuracy(logits, y, topk=(1, 5))
        losses.update(loss.item(), bs)
        top1.update(accuracy['acc1'], bs)
        top5.update(accuracy['acc5'], bs)
        writer.add_scalar('loss/train', loss.item(), global_step=cur_step)
        writer.add_scalar('acc1/train', accuracy['acc1'], global_step=cur_step)
        writer.add_scalar('acc5/train', accuracy['acc5'], global_step=cur_step)

        cur_step += 1

    logger.info('Train: [{:3d}/{}] Prec@(1,5) ({top1.avg:.4%}, {top5.avg:.4%})'.format(
        epoch + 1, config.epochs, top1=top1, top5=top5))


def validate(config, valid_loader, model, criterion, epoch, cur_step, writer):
    top1 = AverageMeter('top1')
    top5 = AverageMeter('top5')
    losses = AverageMeter('losses')

    model.eval()

    with torch.no_grad():
        for step, (X, y) in enumerate(valid_loader):
            X, y = X.to(device), y.to(device)
            bs = X.size(0)

            logits = model(X)
            loss = criterion(logits, y)

            accuracy = utils.accuracy(logits, y, topk=(1, 5))
            losses.update(loss.item(), bs)
            top1.update(accuracy['acc1'], bs)
            top5.update(accuracy['acc5'], bs)

    writer.add_scalar('loss/test', losses.avg, global_step=cur_step)
    writer.add_scalar('acc1/test', top1.avg, global_step=cur_step)
    writer.add_scalar('acc5/test', top5.avg, global_step=cur_step)

    logger.info('Valid: [{:3d}/{}] Prec@(1,5) ({top1.avg:.4%}, {top5.avg:.4%})'.format(
        epoch + 1, config.epochs, top1=top1, top5=top5))

    return top1.avg, top5.avg



for model, optimizer, writer in zip(models, optimizers, writers):

    utils.set_random(666)

    best_top1 = 0.
    best_top5 = 0.
    early_stop = args.early_stop

    for epoch in range(args.epochs):
        drop_prob = args.drop_path_prob * epoch / args.epochs
        model.drop_path_prob(drop_prob)

        # training
        train(args, train_loader, model, optimizer, criterion, epoch, writer)

        # validation
        cur_step = (epoch + 1) * len(train_loader)
        top1, top5 = validate(args, valid_loader, model, criterion, epoch, cur_step, writer)

        # early stopping
        if top1 > best_top1:
            early_stop = args.early_stop
        else:
            early_stop -= 1
            if early_stop == 0:
                break

        best_top1 = max(best_top1, top1)
        best_top5 = max(best_top5, top5)
        
    logger.info('Final best Prec@1 = {:.4%} Prec@5 = {:.4%}'.format(best_top1, best_top5))
