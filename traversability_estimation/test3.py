import matplotlib.pyplot as plt
import numpy as np
import math as m
import torch


X = np.random.random((100, 100)) # sample 2D array
plt.imshow(X, cmap="gray")
plt.show()

print(m.exp(-0.2))

init_lr = 1e-3
final_lr = 1e-5
epoch = 10
lr_decay_epoch = 120

lr = init_lr - (init_lr - final_lr)*(1-m.exp(-epoch/lr_decay_epoch))
print('learning rate' + str(lr))

data1 = np.zeros((3))
bla = 2

data2 = np.append(data1, bla)

print(data2.shape)

t1 = torch.zeros([2, 4], dtype=torch.float32)
print(t1)
print(t1.shape)

t2 = torch.zeros([2, 4], dtype=torch.float32)
print(t2)
print(t2.shape)

t3 = t1.add(t2);

print(t3)
print(t3.shape)
