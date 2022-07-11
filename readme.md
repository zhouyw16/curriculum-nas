# Readme


## Introduction

The code of the ACM MM 2022 paper

Curriculum-NAS: Curriculum Weight-Sharing Neural Architecture Search

<img src="docs/framework.png">

The code is developed based on [XAutoDL](https://github.com/D-X-Y/AutoDL-Projects).


# Requirements

1. python >= 3.6

2. pytorch >= 1.9.0


## To Run the code

1. Clone the repository

```bash
git clone https://github.com/zhouyw16/curriculum-nas.git
```

2. Setup the environment

```bash
cd curriculum-nas
export TORCH_HOME=<datasets and XAutoDL benchmark files>
```
For example, if there is a directory named 'torch_home', which contains cifar-10-batches-py, cifar-100-python, ImageNet16 and NATS-sss-v1_0-50262-simple. Then it needs to be exported as an environment variable TORCH_HOME.

The three datasets directories can be automatically installed. The benchmark directory should be manually downloaded from the link provided in the Readme file of [NATS-Bench](https://github.com/D-X-Y/NATS-Bench).

3. Modify the XAutoDL module
```bash
pip install xautodl
```

Before running the code, it is necessary to add/modify some specific functions in xautodl library. Generally, the path of the files modified below is /usr/lib/python/site-packages/xautodl. A easy way is to jump to the definition of the following functions with the help of your IDE.

```python
# Modify: xautodl/utils/evaluation_utils.py
def obtain_accuracy(output, target, topk=(1,)):
    """Computes the precision@k for the specified values of k"""
    maxk = max(topk)
    batch_size = target.size(0)

    _, pred = output.topk(maxk, 1, True, True)
    pred = pred.t()
    correct = pred.eq(target.view(1, -1).expand_as(pred))

    res = []
    for k in topk:
        correct_k = correct[:k].reshape(-1).float().sum(0, keepdim=True)
        res.append(correct_k.mul_(100.0 / batch_size))
    return res

# Modify: xautodl/procedures/optimizers.py
def get_optim_scheduler(parameters, config, two_criterion=False):
    ......
    if config.criterion == "Softmax":
        criterion = torch.nn.CrossEntropyLoss()
        w_criterion = torch.nn.CrossEntropyLoss(reduction='none')
    elif config.criterion == "SmoothSoftmax":
        criterion = CrossEntropyLabelSmooth(config.class_num, config.label_smooth)
        w_criterion = CrossEntropyLabelSmooth(config.class_num, config.label_smooth, reduction='none')
    else:
        raise ValueError("invalid criterion : {:}".format(config.criterion))
    if two_criterion:
        return optim, scheduler, criterion, w_criterion
    ......

# Add: xautodl/models/cell_searchs/generic_model.py/class GenericNAS201Model
    def return_rank(self, arch):
        archs = Structure.gen_all(self._op_names, self._max_nodes, False)
        pairs = [(self.get_log_prob(a), a) for a in archs]
        sorted_pairs = sorted(pairs, key=lambda x: -x[0])
        n = len(sorted_pairs)
        for i, pair in enumerate(sorted_pairs):
            p, a = pair
            if arch == a.tostr():
                return i, n
        return -1, n

```


4. Run
```bash
<CUDA_VISIBLE_DEVICES=0> python search_ws.py --dataset cifar10 --data_path $TORCH_HOME/cifar.python --algo darts-v1 --rand_seed 777 --subnet_candidate_num 5
```

5. Batch Run
```bash
bash run-ws.sh
```
