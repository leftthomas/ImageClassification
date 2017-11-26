import argparse

import torch
import torch.nn as nn
import torchnet as tnt
from torch.autograd import Variable
from torch.optim import Adam
from torchnet.engine import Engine
from torchnet.logger import VisdomPlotLogger, VisdomLogger
from tqdm import tqdm

import utils
from averagevaluemeter import AverageValueMeter
from model import SquashCapsuleNet


def processor(sample):
    data, labels, training = sample

    data = Variable(data)
    labels = Variable(labels)
    if torch.cuda.is_available():
        data = data.cuda()
        labels = labels.cuda()

    classes = model(data)
    loss = loss_criterion(classes, labels)

    return loss, classes


def on_sample(state):
    state['sample'].append(state['train'])


def reset_meters():
    meter_accuracy.reset()
    meter_loss.reset()
    confusion_meter.reset()


def on_forward(state):
    meter_accuracy.add(state['output'].data, state['sample'][1])
    confusion_meter.add(state['output'].data, state['sample'][1])
    meter_loss.add(state['loss'].data[0])


def on_start_epoch(state):
    reset_meters()
    state['iterator'] = tqdm(state['iterator'])


def on_end_epoch(state):
    print('[Epoch %d] Training Loss: %.4f (Accuracy: %.2f%%)' % (
        state['epoch'], meter_loss.value(), meter_accuracy.value()[0]))

    train_loss_logger.log(state['epoch'], meter_loss.value())
    train_accuracy_logger.log(state['epoch'], meter_accuracy.value()[0])

    reset_meters()

    engine.test(processor, utils.get_iterator(False, DATA_TYPE))

    test_loss_logger.log(state['epoch'], meter_loss.value())
    test_accuracy_logger.log(state['epoch'], meter_accuracy.value()[0])
    confusion_logger.log(confusion_meter.value())

    print('[Epoch %d] Testing Loss: %.4f (Accuracy: %.2f%%)' % (
        state['epoch'], meter_loss.value(), meter_accuracy.value()[0]))

    torch.save(model.state_dict(), 'epochs/epoch_%d.pt' % state['epoch'])


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Train Capsule Classfication')
    parser.add_argument('--data_type', default='MNIST', type=str,
                        choices=['MNIST', 'CIFAR10', 'CIFAR100', 'STL10', 'SVHN'],
                        help='dataset type')
    parser.add_argument('--num_epochs', default=100, type=int, help='train epochs number')

    opt = parser.parse_args()

    NUM_EPOCHS = opt.num_epochs
    DATA_TYPE = opt.data_type

    if DATA_TYPE == 'MNIST':
        in_channels = 1
    else:
        in_channels = 3
    if DATA_TYPE == 'CIFAR100':
        CLASSES = 100
    else:
        CLASSES = 10
    model = SquashCapsuleNet(in_channels, CLASSES)
    if torch.cuda.is_available():
        model = model.cuda()

    print("# parameters:", sum(param.numel() for param in model.parameters()))

    optimizer = Adam(model.parameters())

    engine = Engine()
    meter_loss = AverageValueMeter()
    meter_accuracy = tnt.meter.ClassErrorMeter(accuracy=True)
    confusion_meter = tnt.meter.ConfusionMeter(CLASSES, normalized=True)

    train_loss_logger = VisdomPlotLogger('line', opts={'title': 'Train Loss'})
    train_accuracy_logger = VisdomPlotLogger('line', opts={'title': 'Train Accuracy'})
    test_loss_logger = VisdomPlotLogger('line', opts={'title': 'Test Loss'})
    test_accuracy_logger = VisdomPlotLogger('line', opts={'title': 'Test Accuracy'})
    confusion_logger = VisdomLogger('heatmap', opts={'title': 'Confusion Matrix',
                                                     'columnnames': list(range(CLASSES)),
                                                     'rownames': list(range(CLASSES))})
    loss_criterion = nn.CrossEntropyLoss()

    engine.hooks['on_sample'] = on_sample
    engine.hooks['on_forward'] = on_forward
    engine.hooks['on_start_epoch'] = on_start_epoch
    engine.hooks['on_end_epoch'] = on_end_epoch

    engine.train(processor, utils.get_iterator(True, DATA_TYPE), maxepoch=NUM_EPOCHS, optimizer=optimizer)
