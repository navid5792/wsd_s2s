import pickle
import numpy as np
tar_pos = ['nn','rb','jj','vb']

with open("TRUE_PRED_POS_POS.pkl","rb") as f:
    y_true,y_pred,y_pos = pickle.load(f)

with open("vocab.pkl","rb") as f:
    word2index,index2word = pickle.load(f)

pos_list = list(set(y_pos))
pos2acc = dict()

for x in pos_list:
    tot = 0
    correct = 0
    for i in range(len(y_true)):
        if y_pos[i] == x:
            tot +=1
            if y_pred[i] == y_true[i]:
                correct +=1
    acc = correct/tot
    pos2acc[index2word[x]] = (acc,tot)
    #print(index2word[x], "--->",acc,tot)

posclass2acc = dict()
f = open("start_pos_acc.txt","w")
for x in tar_pos:
    list_pos = [p for p in pos2acc.keys() if p.startswith(x)]
    #print(list_pos)
    acc = 0
    total = 0
    for y in list_pos:
        tup = pos2acc[y]
        acc = acc + tup[0]
        total = total + tup[1]
    print(x,"--->",acc/len(list_pos),total)
    f.write((str(x) + '--->'+str(acc/len(list_pos))+"  sample:  "+str(total) + '\n'))
    
    posclass2acc[y] = (acc/len(list_pos),total)
f.close()