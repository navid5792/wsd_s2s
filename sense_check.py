index = []
target = []
for i in range(len(test_pairs)):
    x = test_pairs[i][0].split()
    y = test_pairs[i][1].split()
    temp =[]
    temp_target = []
    for j in range(len(x)):
        if x[j] != y[j]:
            temp.append(j)
            temp_target.append(y[j])
    index.append(temp)
    target.append(temp_target)

y_true=[]
y_pred=[]
for i in range(len(result_x)):
    for j in range(len(result_x[i])):
        if result_x[i][j].isdigit() and len(result_x[i][j]) == 10:
            y_true.append(result_x[i][j])
            y_pred.append(result_y[i][j])

from sklearn.metrics import f1_score
f1 = f1_score(y_true,y_pred,average='micro')
print(f1)