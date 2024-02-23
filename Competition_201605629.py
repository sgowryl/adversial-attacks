############################################################################
### Written by Gaojie Jin and updated by Xiaowei Huang, 2021
###
### For a 2-nd year undergraduate student competition on
### the robustness of deep neural networks, where a student
### needs to develop
### 1. an attack algorithm, and
### 2. an adversarial training algorithm
###
### The score is based on both algorithms.
############################################################################


import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
import torch.optim as optim
import torchvision
from torchvision import transforms
from torch.autograd import Variable
import argparse
import time
import copy

# input id
id_ = 201605629
epsilon = 0.3
alpha = 0.00784

# setup training parameters
parser = argparse.ArgumentParser(description="PyTorch MNIST Training")
parser.add_argument(
    "--batch-size",
    type=int,
    default=128,
    metavar="N",
    help="input batch size for training (default: 128)",
)
parser.add_argument(
    "--test-batch-size",
    type=int,
    default=128,
    metavar="N",
    help="input batch size for testing (default: 128)",
)
parser.add_argument(
    "--epochs", type=int, default=10, metavar="N", help="number of epochs to train"
)
parser.add_argument(
    "--lr", type=float, default=0.01, metavar="LR", help="learning rate"
)
parser.add_argument(
    "--no-cuda", action="store_true", default=False, help="disables CUDA training"
)
parser.add_argument(
    "--seed", type=int, default=1, metavar="S", help="random seed (default: 1)"
)


args = parser.parse_args(args=[])

# judge cuda is available or not
use_cuda = not args.no_cuda and torch.cuda.is_available()
# device = torch.device("cuda" if use_cuda else "cpu")
device = torch.device("cpu")

torch.manual_seed(args.seed)
kwargs = {"num_workers": 1, "pin_memory": True} if use_cuda else {}

############################################################################
################    don't change the below code    #####################
############################################################################
train_set = torchvision.datasets.FashionMNIST(
    root="data",
    train=True,
    download=True,
    transform=transforms.Compose([transforms.ToTensor()]),
)
train_loader = DataLoader(train_set, batch_size=args.batch_size, shuffle=True)

test_set = torchvision.datasets.FashionMNIST(
    root="data",
    train=False,
    download=True,
    transform=transforms.Compose([transforms.ToTensor()]),
)
test_loader = DataLoader(test_set, batch_size=args.batch_size, shuffle=True)

# define fully connected network
class Net(nn.Module):
    def __init__(self):
        super(Net, self).__init__()
        self.fc1 = nn.Linear(28 * 28, 128)
        self.fc2 = nn.Linear(128, 64)
        self.fc3 = nn.Linear(64, 32)
        self.fc4 = nn.Linear(32, 10)

    def forward(self, x):
        x = self.fc1(x)
        x = F.relu(x)
        x = self.fc2(x)
        x = F.relu(x)
        x = self.fc3(x)
        x = F.relu(x)
        x = self.fc4(x)
        output = F.log_softmax(x, dim=1)
        return output


##############################################################################
#############    end of "don't change the below code"   ######################
##############################################################################


def fgsm_attack(X, epsilon, data_grad):
    sign_grad = data_grad.sign()
    X_adv = X
    X_adv += epsilon * sign_grad
    X_adv = torch.clamp(X_adv, 0, 1)
    return X_adv


class LinPGDAttack(object):
    def __init__(self, model):
        self.model = model

    def perturb(self, x_natural, y):
        x = x_natural.detach()
        x += torch.zeros_like(x).uniform_(-epsilon, epsilon)
        for i in range(7):
            x.requires_grad = True
            with torch.enable_grad():
                logits = self.model(x)
                loss = F.cross_entropy(logits, y)
            grad = torch.autograd.grad(loss, [x])[0]
            x = x.detach() + alpha * torch.sign(grad.detach())
            x = torch.min(torch.max(x, x_natural - epsilon), x_natural + epsilon)
            x = torch.clamp(x, 0, 1)
        return x


def linPGDAttack(x, y, model, adversary):
    adv = adversary.perturb(x, y)
    return adv


# generate adversarial data, you can define your adversarial method
def adv_attack(model, X, y, device):
    X_adv = Variable(X.data, requires_grad=True)

    ################################################################################################
    ## Note: below is the place you need to edit to implement your own attack algorithm
    ################################################################################################

    random_noise = torch.FloatTensor(*X_adv.shape).uniform_(-0.1, 0.1).to(device)
    X_adv = Variable(X_adv.data + random_noise)

    ################################################################################################
    ## end of attack method
    ################################################################################################

    return X_adv


# train function, you can use adversarial training
def train(args, model, device, train_loader, optimizer, epoch):
    model.train()
    correct = 0
    for batch_idx, (data, target) in enumerate(train_loader):
        data, target = data.to(device), target.to(device)
        data = data.view(data.size(0), 28 * 28)

        # use adverserial data to train the defense model
        adv_data = adv_attack(model, data, target, device=device)
        # adv_data_grad = adv_data.data
        # adv_data = fgsm_attack(data,epsilon, adv_data_grad)
        adv_data = linPGDAttack(
            data, target, model, LinPGDAttack(model)
        )  # adv train 2  USE SHELF LIB MTHS TO TEST ROBUSTNESS

        # clear gradients
        optimizer.zero_grad()

        # compute loss
        loss = F.cross_entropy(
            model(adv_data), target
        )  # adv train 0 feed adv_x in net training to shape a resilient net
        output = model(data)
        pred = output.max(1, keepdim=True)[1]
        correct += pred.eq(target.view_as(pred)).sum().item()
        # loss = F.nll_loss(model(adv_data), target)
        # loss = F.nll_loss(model(data), target)

        # get gradients and update
        loss.backward()
        optimizer.step()


# predict function
def eval_test(model, device, test_loader):
    model.eval()
    test_loss = 0
    correct = 0
    with torch.no_grad():
        for data, target in test_loader:
            data, target = data.to(device), target.to(device)
            data = data.view(data.size(0), 28 * 28)
            output = model(data)
            test_loss += F.nll_loss(output, target, size_average=False).item()
            pred = output.max(1, keepdim=True)[1]
            correct += pred.eq(target.view_as(pred)).sum().item()
    test_loss /= len(test_loader.dataset)
    test_accuracy = correct / len(test_loader.dataset)
    return test_loss, test_accuracy


def eval_adv_test(model, device, test_loader):
    model.eval()
    test_loss = 0
    correct = 0
    with torch.no_grad():
        for data, target in test_loader:
            data, target = data.to(device), target.to(device)
            data = data.view(data.size(0), 28 * 28)
            adv_data = adv_attack(model, data, target, device=device)
            output = model(adv_data)
            test_loss += F.nll_loss(output, target, size_average=False).item()
            pred = output.max(1, keepdim=True)[1]
            correct += pred.eq(target.view_as(pred)).sum().item()
    test_loss /= len(test_loader.dataset)
    test_accuracy = correct / len(test_loader.dataset)
    return test_loss, test_accuracy


# main function, train the dataset and print train loss, test loss for each epoch
def train_model():
    model = Net().to(device)

    ################################################################################################
    ## Note: below is the place you need to edit to implement your own training algorithm
    ##       You can also edit the functions such as train(...).
    ################################################################################################

    optimizer = optim.SGD(
        model.parameters(), lr=args.lr, momentum=0.9, weight_decay=0.0002
    )
    for epoch in range(1, args.epochs + 1):
        start_time = time.time()

        # training
        adjust_learning_rate(optimizer, epoch)
        train(args, model, device, train_loader, optimizer, epoch)

        # get trnloss and testloss
        trnloss, trnacc = eval_test(model, device, train_loader)
        advloss, advacc = eval_adv_test(model, device, train_loader)

        # print trnloss and testloss
        print(
            "Epoch " + str(epoch) + ": " + str(int(time.time() - start_time)) + "s",
            end=", ",
        )
        print(
            "trn_loss: {:.4f}, trn_acc: {:.2f}%".format(trnloss, 100.0 * trnacc),
            end=", ",
        )
        print("adv_loss: {:.4f}, adv_acc: {:.2f}%".format(advloss, 100.0 * advacc))

    adv_tstloss, adv_tstacc = eval_adv_test(model, device, test_loader)
    print(
        "Your estimated attack ability, by applying your attack method on your own trained model, is: {:.4f}".format(
            1 / adv_tstacc
        )
    )
    print(
        "Your estimated defence ability, by evaluating your own defence model over your attack, is: {:.4f}".format(
            adv_tstacc
        )
    )
    ################################################################################################
    ## end of training method
    ################################################################################################

    # save the model
    torch.save(model.state_dict(), str(id_) + ".pt")
    return model


# hyper-para tune [adv train 0]
def adjust_learning_rate(optimizer, epoch):
    lr = args.lr
    if epoch >= 100:
        lr /= 10
    if epoch >= 150:
        lr /= 10
    for param_group in optimizer.param_groups:
        param_group["lr"] = lr


# compute perturbation distance
def p_distance(model, train_loader, device):
    p = []
    for batch_idx, (data, target) in enumerate(train_loader):
        data, target = data.to(device), target.to(device)
        data = data.view(data.size(0), 28 * 28)
        data_ = copy.deepcopy(data.data)
        adv_data = adv_attack(model, data, target, device=device)
        p.append(torch.norm(data_ - adv_data, float("inf")))
    print("epsilon p: ", max(p))


################################################################################################
## Note: below is for testing/debugging purpose, please comment them out in the submission file
################################################################################################

# Comment out the following command when you do not want to re-train the model
# In that case, it will load a pre-trained model you saved in train_model()
model = train_model()

# Call adv_attack() method on a pre-trained model'
# the robustness of the model is evaluated against the infinite-norm distance measure
# important: MAKE SURE the infinite-norm distance (epsilon p) less than 0.11 !!!
p_distance(model, train_loader, device)
