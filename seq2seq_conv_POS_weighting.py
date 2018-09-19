import unicodedata
import string
import re
import random
import time
import datetime
import math
import socket
hostname = socket.gethostname()
import pickle
import torch
import torch.nn as nn
from torch.autograd import Variable
from torch import optim
import torch.nn.functional as F
from torch.nn.utils.rnn import pad_packed_sequence, pack_padded_sequence#, masked_cross_entropy
from masked_cross_entropy import *

#import matplotlib.pyplot as plt
#import matplotlib.ticker as ticker
import numpy as np

import sys

USE_CUDA = True

PAD_token = 0
SOS_token = 1
EOS_token = 2

class Lang:
    def __init__(self, name):
        self.name = name
        self.trimmed = False
        self.word2index = {}
        self.word2count = {}
        self.index2word = {0: "PAD", 1: "SOS", 2: "EOS"}
        self.n_words = 3 # Count default tokens

    def index_words(self, sentence):
        for word in sentence.split():
            self.index_word(word)

    def index_word(self, word):
        if word not in self.word2index:
            self.word2index[word] = self.n_words
            self.word2count[word] = 1
            self.index2word[self.n_words] = word
            self.n_words += 1
        else:
            self.word2count[word] += 1

    # Remove words below a certain count threshold
    def trim(self, min_count):
        if self.trimmed: return
        self.trimmed = True
        
        keep_words = []
        
        for k, v in self.word2count.items():
            if v >= min_count:
                keep_words.append(k)

        print('keep_words %s / %s = %.4f' % (
            len(keep_words), len(self.word2index), len(keep_words) / len(self.word2index)
        ))

        # Reinitialize dictionaries
        self.word2index = {}
        self.word2count = {}
        self.index2word = {0: "PAD", 1: "SOS", 2: "EOS"}
        self.n_words = 3 # Count default tokens

        for word in keep_words:
            self.index_word(word)



# Turn a Unicode string to plain ASCII, thanks to http://stackoverflow.com/a/518232/2809427
def unicode_to_ascii(s):
    return ''.join(
        c for c in unicodedata.normalize('NFD', s)
        if unicodedata.category(c) != 'Mn'
    )

# Lowercase, trim, and remove non-letter characters
def normalize_string(s):
    s = unicode_to_ascii(s.lower().strip())
    s = s.strip()
    return s

def read_langs(lang1, lang2, data_dir, reverse=False):
    print("Reading lines...")

    # Read the file and split into lines
    filename = data_dir
    lines = open(filename).read().strip().split('\n')

    # Split every line into pairs and normalize
    pairs = [[normalize_string(s) for s in l.split('\t')] for l in lines]

    # Reverse pairs, make Lang instances
    if reverse:
        pairs = [list(reversed(p)) for p in pairs]
        input_lang = Lang(lang2)
        output_lang = Lang(lang1)
    else:
        input_lang = Lang(lang1)
        output_lang = Lang(lang2)

    return input_lang, output_lang, pairs

MIN_LENGTH = 3
MAX_LENGTH = 20

def filter_pairs(pairs):
    filtered_pairs = []
    for pair in pairs:
        if len(pair[0]) >= MIN_LENGTH and len(pair[0]) <= MAX_LENGTH \
            and len(pair[1]) >= MIN_LENGTH and len(pair[1]) <= MAX_LENGTH:
                filtered_pairs.append(pair)
    return filtered_pairs



def prepare_data(lang1_name, lang2_name, data_dir, reverse=False):
    input_lang, output_lang, pairs = read_langs(lang1_name, lang2_name, data_dir, reverse)
    print("Read %d sentence pairs" % len(pairs))
    
    # pairs = filter_pairs(pairs)
    print("Filtered to %d pairs" % len(pairs))
    
    print("Indexing words...")
    for pair in pairs: 
        input_lang.index_words(pair[0])
        output_lang.index_words(pair[1])
    
    print('Indexed %d words in input language, %d words in output' % (input_lang.n_words, output_lang.n_words))
    return input_lang, output_lang, pairs

#load every pair and POS together

dicts = "all_pos.txt"
input_lang, output_lang, pairs0 = prepare_data('all_w', 'all_s', dicts, False)


#load normal train and test data

train_data = "train.txt"
input_lang0, output_lang0, pairs = prepare_data('train_w', 'train_s', train_data, False)


test_data = "test.txt"
input_lang0, output_lang0, test_pairs = prepare_data('test_w', 'test_s', test_data, False)

#load POS train and test data

train_data = "train_pos.txt"
input_lang0, output_lang0, pairs_pos = prepare_data('train_w_pos', 'train_s_pos', train_data, False)


test_data = "test_pos.txt"
input_lang0, output_lang0, test_pairs_pos = prepare_data('test_w_pos', 'test_s_pos', test_data, False)

#####################################

MIN_COUNT = 1

# input_lang.trim(MIN_COUNT)
# output_lang.trim(MIN_COUNT)

# print('Indexed %d words in input language, %d words in output' % (input_lang.n_words, output_lang.n_words))
keep_pairs = []

def indexes_from_sentence(lang, sentence):
    return [lang.word2index[word] for word in sentence.split()] + [EOS_token]

# Pad a with the PAD symbol
def pad_seq(seq, max_length):
    seq += [PAD_token for i in range(max_length - len(seq))]
    return seq

def random_batch(batch_size, pairs):
    input_seqs = []
    target_seqs = []
    pos_seqs = []

    # Choose random pairs
    for i in range(batch_size):
        pair = random.choice(pairs)
        input_seqs.append(indexes_from_sentence(input_lang, pair[0]))
        target_seqs.append(indexes_from_sentence(output_lang, pair[1]))
        pos_seqs.append(indexes_from_sentence(input_lang, pair[2]))

    # Zip into pairs, sort by length (descending), unzip
    seq_pairs = sorted(zip(input_seqs, target_seqs, pos_seqs), key=lambda p: len(p[0]), reverse=True)
    input_seqs, target_seqs, pos_seqs = zip(*seq_pairs)
    
    # For input and target sequences, get array of lengths and pad with 0s to max length
    input_lengths = [len(s) for s in input_seqs]
    input_padded = [pad_seq(s, max(input_lengths)) for s in input_seqs]
    
    target_lengths = [len(s) for s in target_seqs]
    target_padded = [pad_seq(s, max(target_lengths)) for s in target_seqs]
    
    pos_lengths = [len(s) for s in pos_seqs]
    pos_padded = [pad_seq(s, max(pos_lengths)) for s in pos_seqs]

    # Turn padded arrays into (batch_size x max_len) tensors, transpose into (max_len x batch_size)
    input_var = Variable(torch.LongTensor(input_padded)).transpose(0, 1)
    target_var = Variable(torch.LongTensor(target_padded)).transpose(0, 1)
    pos_var = Variable(torch.LongTensor(pos_padded)).transpose(0, 1)
    
    if USE_CUDA:
        input_var = input_var.cuda()
        target_var = target_var.cuda()
        pos_var = pos_var.cuda()
        
    return input_var, input_lengths, target_var, target_lengths, pos_var, pos_lengths

# print(random_batch(2))



class EncoderRNN(nn.Module):
    def __init__(self, input_size, hidden_size, n_layers=1, dropout=0.1):
        super(EncoderRNN, self).__init__()
        
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.n_layers = n_layers
        self.dropout = dropout
        self.conv = nn.Conv1d(300,300,2,stride=1)
        self.embedding = nn.Embedding(input_size, hidden_size)
        self.gru = nn.GRU(hidden_size, hidden_size, n_layers, dropout=self.dropout, bidirectional=True)
        
    def forward(self, input_seqs, input_lengths, which, hidden=None):
        # Note: we run this all at once (over multiple batches of multiple sequences)
        if which == 'conv':
            start = torch.FloatTensor([1]*input_seqs.size(1)).view(1,-1)
            input_seqs = torch.cat([input_seqs.cpu().float().data,start],0).long().cuda()
            input_seqs = Variable(input_seqs)
               
            embedded = self.embedding(input_seqs)
            embedded = self.conv(embedded.transpose(0,1).transpose(1,2))
            embedded = embedded.transpose(1,2).transpose(0,1)
        else:
            embedded = self.embedding(input_seqs)
        
        packed = torch.nn.utils.rnn.pack_padded_sequence(embedded, input_lengths)
        #print(packed)
        outputs, hidden = self.gru(packed, hidden)
        outputs, output_lengths = torch.nn.utils.rnn.pad_packed_sequence(outputs) # unpack (back to padded)
        outputs = outputs[:, :, :self.hidden_size] + outputs[:, : ,self.hidden_size:] # Sum bidirectional outputs
        return outputs, hidden

class Attn(nn.Module):
    def __init__(self, method, hidden_size):
        super(Attn, self).__init__()
        
        self.method = method
        self.hidden_size = hidden_size
        
        if self.method == 'general':
            self.attn = nn.Linear(self.hidden_size, hidden_size)

        elif self.method == 'concat':
            self.attn = nn.Linear(self.hidden_size * 2, hidden_size)
            self.v = nn.Parameter(torch.FloatTensor(1, hidden_size))

    def forward(self, hidden, encoder_outputs):
        max_len = encoder_outputs.size(0)
        this_batch_size = encoder_outputs.size(1)

        # Create variable to store attention energies
        attn_energies = Variable(torch.zeros(this_batch_size, max_len)) # B x S

        if USE_CUDA:
            attn_energies = attn_energies.cuda()

        # For each batch of encoder outputs
        for b in range(this_batch_size):
            # Calculate energy for each encoder output
            for i in range(max_len):
                attn_energies[b, i] = self.score(hidden[:, b], encoder_outputs[i, b].unsqueeze(0))

        # Normalize energies to weights in range 0 to 1, resize to 1 x B x S
        return F.softmax(attn_energies).unsqueeze(1)
    
    def score(self, hidden, encoder_output):
        
        if self.method == 'dot':
            energy = hidden.dot(encoder_output)
            return energy
        
        elif self.method == 'general':
            energy = self.attn(encoder_output)
            energy = hidden.dot(energy)
            return energy
        
        elif self.method == 'concat':
            energy = self.attn(torch.cat((hidden, encoder_output), 1))
            energy = self.v.dot(energy)
            return energy



class BahdanauAttnDecoderRNN(nn.Module):
    def __init__(self, hidden_size, output_size, n_layers=1, dropout_p=0.1):
        super(BahdanauAttnDecoderRNN, self).__init__()
        
        # Define parameters
        self.hidden_size = hidden_size
        self.output_size = output_size
        self.n_layers = n_layers
        self.dropout_p = dropout_p
        self.max_length = max_length
        
        # Define layers
        self.embedding = nn.Embedding(output_size, hidden_size)
        self.dropout = nn.Dropout(dropout_p)
        self.attn = Attn('concat', hidden_size)
        self.gru = nn.GRU(hidden_size, hidden_size, n_layers, dropout=dropout_p)
        self.out = nn.Linear(hidden_size, output_size)
    
    def forward(self, word_input, last_hidden, encoder_outputs):
        # Note: we run this one step at a time
        # TODO: FIX BATCHING
        
        # Get the embedding of the current input word (last output word)
        word_embedded = self.embedding(word_input).view(1, 1, -1) # S=1 x B x N
        word_embedded = self.dropout(word_embedded)
        
        # Calculate attention weights and apply to encoder outputs
        attn_weights = self.attn(last_hidden[-1], encoder_outputs)
        context = attn_weights.bmm(encoder_outputs.transpose(0, 1)) # B x 1 x N
        context = context.transpose(0, 1) # 1 x B x N
        
        # Combine embedded input word and attended context, run through RNN
        rnn_input = torch.cat((word_embedded, context), 2)
        output, hidden = self.gru(rnn_input, last_hidden)
        
        # Final output layer
        output = output.squeeze(0) # B x N
        output = F.log_softmax(self.out(torch.cat((output, context), 1)))
        
        # Return final output, hidden state, and attention weights (for visualization)
        return output, hidden, attn_weights

class LuongAttnDecoderRNN(nn.Module):
    def __init__(self, attn_model, hidden_size, output_size, n_layers=1, dropout=0.1):
        super(LuongAttnDecoderRNN, self).__init__()

        # Keep for reference
        self.attn_model = attn_model
        self.hidden_size = hidden_size
        self.output_size = output_size
        self.n_layers = n_layers
        self.dropout = dropout

        # Define layers
        self.embedding = nn.Embedding(output_size, hidden_size)
        self.embedding_dropout = nn.Dropout(dropout)
        self.gru = nn.GRU(hidden_size, hidden_size, n_layers, dropout=dropout)
        self.concat = nn.Linear(hidden_size * 2, hidden_size)
        self.out = nn.Linear(hidden_size, output_size)
        self.W1 = nn.Parameter(torch.FloatTensor([0.2]).cuda(),requires_grad =True)
        self.W2 = nn.Parameter(torch.FloatTensor([0.6]).cuda(),requires_grad =True)
        self.W3 = nn.Parameter(torch.FloatTensor([0.2]).cuda(),requires_grad =True)
        #nn.ParameterList.append(self.,self.W1)
        #nn.ParameterList.append(,self.W2)
        # Choose attention model
        if attn_model != 'none':
            self.attn = Attn(attn_model, hidden_size)
    
    def get_W(self):
        return (self.W1,self.W2)
    
    def forward(self, input_seq, last_hidden, last_hidden_pos, last_hidden_conv,encoder_outputs, encoder_outputs_pos,encoder_outputs_conv):
        # Note: we run this one step at a time

        # Get the embedding of the current input word (last output word)
        batch_size = input_seq.size(0)
        embedded = self.embedding(input_seq)
        embedded = self.embedding_dropout(embedded)
        embedded = embedded.view(1, batch_size, self.hidden_size) # S=1 x B x N

        # Get current hidden state from input word and last hidden state
        rnn_output, hidden = self.gru(embedded, last_hidden)
        rnn_output_pos, hidden_pos = self.gru(embedded, last_hidden_pos)
        rnn_output_conv, hidden_conv = self.gru(embedded, last_hidden_conv)
        # Calculate attention from current RNN state and all encoder outputs;
        # apply to encoder outputs to get weighted average
        attn_weights = self.attn(rnn_output, encoder_outputs)
        attn_weights_pos = self.attn(rnn_output_pos, encoder_outputs_pos)
        attn_weights_conv = self.attn(rnn_output_conv,encoder_outputs_conv)
        #print(attn_weights)
        
    # with fixed impact of attn
#        attn_weights = F.softmax(attn_weights.squeeze(1) * attn_weights_pos.squeeze(1)).unsqueeze(1) 
        attn_weights = F.softmax(self.W1*attn_weights.squeeze(1) + self.W2*attn_weights_pos.squeeze(1) + self.W3*attn_weights_conv.squeeze(1)).unsqueeze(1)
        
    #using neural net to figure out the best ratio
#        self.f_c = nn.Linear(batch_size*attn_weights.size(2)*2,batch_size*attn_weights.size(2))
#        temp = torch.cat([attn_weights.view(-1,1).cpu().float(),attn_weights_pos.view(-1,1).cpu().float()],0).transpose(0,1)
#        #print(temp)
#        weights = self.f_c(temp).view(batch_size,attn_weights.size(2)).unsqueeze(1) 
#        #print(weights)
#        attn_weights = weights.cuda()
#        
        context = attn_weights.bmm(encoder_outputs.transpose(0, 1)) # B x S=1 x N

        # Attentional vector using the RNN hidden state and context vector
        # concatenated together (Luong eq. 5)
        rnn_output = rnn_output.squeeze(0) # S=1 x B x N -> B x N
        context = context.squeeze(1)       # B x S=1 x N -> B x N
        concat_input = torch.cat((rnn_output, context), 1)
        concat_output = F.tanh(self.concat(concat_input))

        # Finally predict next token (Luong eq. 6, without softmax)
        output = self.out(concat_output)

        # Return final output, hidden state, and attention weights (for visualization)
        
#        print("W1: ",self. W1.grad, "W2 = ", self.W2.grad)
        return output, hidden, hidden_pos,hidden_conv, attn_weights



ALL_W = []
LR = Variable(torch.FloatTensor([0.1]).cuda(),requires_grad =False)
def train(input_batches, input_lengths, target_batches, target_lengths, pos_batches, pos_lengths, encoder, decoder, encoder_optimizer, decoder_optimizer, criterion, max_length=MAX_LENGTH):
    
    # Zero gradients of both optimizers
    encoder_optimizer.zero_grad()
    decoder_optimizer.zero_grad()
    loss = 0 # Added onto for each word

    # Run words through encoder
    encoder_outputs, encoder_hidden = encoder(input_batches, input_lengths,"nor", None)
    
    encoder_outputs_pos, encoder_hidden_pos = encoder(pos_batches, pos_lengths,'POS', None)
    
    encoder_outputs_conv, encoder_hidden_conv = encoder(input_batches, input_lengths,'conv', None)
    
    # Prepare input and output variables
    decoder_input = Variable(torch.LongTensor([SOS_token] * batch_size))
    decoder_hidden = encoder_hidden[:decoder.n_layers] # Use last (forward) hidden state from encoder
    decoder_hidden_pos = encoder_hidden_pos[:decoder.n_layers]
    decoder_hidden_conv = encoder_hidden_conv[:decoder.n_layers]
    
    max_target_length = max(target_lengths)
    all_decoder_outputs = Variable(torch.zeros(max_target_length, batch_size, decoder.output_size))

    # Move new Variables to CUDA
    if USE_CUDA:
        decoder_input = decoder_input.cuda()
        all_decoder_outputs = all_decoder_outputs.cuda()
        
    #print(" Current W1: ",decoder.W1.data, "Current W2 = ", decoder.W2.data)        
    # Run through decoder one time step at a time
    for t in range(max_target_length):
        decoder_output, decoder_hidden, decoder_hidden_pos,decoder_hidden_conv, decoder_attn = decoder(
            decoder_input, decoder_hidden, decoder_hidden_pos,decoder_hidden_conv, encoder_outputs, encoder_outputs_pos,encoder_outputs_conv
        )

        all_decoder_outputs[t] = decoder_output
        decoder_input = target_batches[t] # Next input is current target
        
    #print("after W1: ",decoder.W1.data, "after W2 = ", decoder.W1.grad)
    try:
        decoder.W1 = decoder.W1.sub(LR*decoder.W1.grad)
        decoder.W2 = decoder.W2.sub(LR*decoder.W2.grad)
        decoder.W3 = decoder.W3.sub(LR*decoder.W3.grad)      
    except Exception as e:
        pass
    
    loss = masked_cross_entropy(
        all_decoder_outputs.transpose(0, 1).contiguous(), # -> batch x seq
        target_batches.transpose(0, 1).contiguous(), # -> batch x seq
        target_lengths
    )
    loss.backward()
    
    # Clip gradient norms
    ec = torch.nn.utils.clip_grad_norm(encoder.parameters(), clip)
    dc = torch.nn.utils.clip_grad_norm(decoder.parameters(), clip)

    # Update parameters with optimizers
    encoder_optimizer.step()
    decoder_optimizer.step()
    ALL_W.append(decoder.get_W())
    
#    print("Grad of W2: ",decoder.W2.grad)
    return loss.data[0], ec, dc,decoder_attn

# Configure models
attn_model = 'dot'
hidden_size = 300
n_layers = 2
dropout = 0.1
# batch_size = 100
batch_size = 100

# Configure training/optimization
clip = 50.0
teacher_forcing_ratio = 0.5
learning_rate = 0.001
decoder_learning_ratio = 5.0
n_epochs = 0
epoch = 0
plot_every = 20
print_every = 100
evaluate_every = 100 #500
ACC_seq = []
ACC_sense = []
ACC_sense_updated = []
decoder_att = []

# Initialize models
encoder = EncoderRNN(input_lang.n_words, hidden_size, n_layers, dropout=dropout)
decoder = LuongAttnDecoderRNN(attn_model, hidden_size, output_lang.n_words, n_layers, dropout=dropout)

# Initialize optimizers and criterion
encoder_optimizer = optim.Adam(encoder.parameters(), lr=learning_rate)
decoder_optimizer = optim.Adam(decoder.parameters(), lr=learning_rate * decoder_learning_ratio)
criterion = nn.CrossEntropyLoss()

# Move models to GPU
if USE_CUDA:
    encoder.cuda()
    decoder.cuda()



# Keep track of time elapsed and running averages
start = time.time()
plot_losses = []
print_loss_total = 0 # Reset every print_every
plot_loss_total = 0 # Reset every plot_every

def as_minutes(s):
    m = math.floor(s / 60)
    s -= m * 60
    return '%dm %ds' % (m, s)

def time_since(since, percent):
    now = time.time()
    s = now - since
    es = s / (percent)
    rs = es - s
    return '%s (- %s)' % (as_minutes(s), as_minutes(rs))

def evaluate(input_seq, pos_seq, max_length=MAX_LENGTH):
    input_lengths = [len(input_seq.split())]
    
    input_seqs = [indexes_from_sentence(input_lang, input_seq)]
    input_batches = Variable(torch.LongTensor(input_seqs), volatile=True).transpose(0, 1)
    
    pos_lengths = [len(pos_seq.split())]
    
    pos_seqs = [indexes_from_sentence(input_lang, pos_seq)]
    pos_batches = Variable(torch.LongTensor(pos_seqs), volatile=True).transpose(0, 1)
    
    if USE_CUDA:
        input_batches = input_batches.cuda()
        pos_batches = pos_batches.cuda()
        
    # Set to not-training mode to disable dropout
    encoder.train(False)
    decoder.train(False)
    
    # Run through encoder
    encoder_outputs, encoder_hidden = encoder(input_batches, input_lengths,"nor", None)
    
    encoder_outputs_pos, encoder_hidden_pos = encoder(pos_batches, pos_lengths,'POS', None)
    
    encoder_outputs_conv, encoder_hidden_conv = encoder(input_batches, input_lengths,'conv', None)
    
    # Create starting vectors for decoder
    decoder_input = Variable(torch.LongTensor([SOS_token]), volatile=True) # SOS
    decoder_hidden = encoder_hidden[:decoder.n_layers] # Use last (forward) hidden state from encoder
    decoder_hidden_pos = encoder_hidden_pos[:decoder.n_layers]
    decoder_hidden_conv = encoder_hidden_conv[:decoder.n_layers]
    if USE_CUDA:
        decoder_input = decoder_input.cuda()

    # Store output words and attention states
    decoded_words = []
    decoder_attentions = torch.zeros(max_length + 1, max_length + 1)
    
    # Run through decoder
    for di in range(max_length):
        decoder_output, decoder_hidden, decoder_hidden_pos,decoder_hidden_conv, decoder_attention = decoder(
            decoder_input, decoder_hidden, decoder_hidden_pos,decoder_hidden_conv, encoder_outputs, encoder_outputs_pos,encoder_outputs_conv
        )
        decoder_attentions[di,:decoder_attention.size(2)] += decoder_attention.squeeze(0).squeeze(0).cpu().data

        # Choose top word from output
        topv, topi = decoder_output.data.topk(1)
        ni = topi[0][0]
        if ni == EOS_token:
            # decoded_words.append('<EOS>')
            break
        else:
            decoded_words.append(output_lang.index2word[ni])
            
        # Next input is chosen word
        decoder_input = Variable(torch.LongTensor([ni]))
        if USE_CUDA: decoder_input = decoder_input.cuda()

    # Set back to training mode
    encoder.train(True)
    decoder.train(True)
    
    return decoded_words, decoder_attentions[:di+1, :len(encoder_outputs)]

def evaluate_randomly():
    [input_sentence, target_sentence, pos] = random.choice(pairs)
    if (len(input_sentence)) > 0:
        evaluate_and_show_attention(input_sentence, pos, target_sentence)

import io
import torchvision
from PIL import Image
#import visdom
# vis = visdom.Visdom()

#def show_plot_visdom():
#    buf = io.BytesIO()
#    plt.savefig(buf)
#    buf.seek(0)
#    attn_win = 'attention (%s)' % hostname
#    vis.image(torchvision.transforms.ToTensor()(Image.open(buf)), win=attn_win, opts={'title': attn_win})
#
#
#
#def show_attention(input_sentence, output_words, attentions):
#    # Set up figure with colorbar
#    fig = plt.figure()
#    ax = fig.add_subplot(111)
#    cax = ax.matshow(attentions.numpy(), cmap='bone')
#    fig.colorbar(cax)
#
#    # Set up axes
#    ax.set_xticklabels([''] + input_sentence.split(' ') + ['<EOS>'], rotation=90)
#    ax.set_yticklabels([''] + output_words)
#
#    # Show label at every tick
#    ax.xaxis.set_major_locator(ticker.MultipleLocator(1))
#    ax.yaxis.set_major_locator(ticker.MultipleLocator(1))
#
#    show_plot_visdom()
#    plt.show()
#    plt.close()

def evaluate_and_show_attention(input_sentence, pos, target_sentence=None):
    output_words, attentions = evaluate(input_sentence, pos)
    output_sentence = ' '.join(output_words)
    print('>', input_sentence)
    if target_sentence is not None:
        print('=', target_sentence)
    print('<', output_sentence)
    if (output_sentence == target_sentence):
        print('True')
    else:
        print('False')
    
    # show_attention(input_sentence, output_words, attentions)
    
    # # Show input, target, output text in visdom
    # win = 'evaluted (%s)' % hostname
    # text = '<p>&gt; %s</p><p>= %s</p><p>&lt; %s</p>' % (input_sentence, target_sentence, output_sentence)
    # vis.text(text, win=win, opts={'title': win})

def evaluate_pairs(test_pairs):
    length = len(test_pairs)
    right_num = 0
    accuracy = 0.0
    for i in range(length):
        [input_sentence, target_sentence, pos] = test_pairs[i]
        if (len(input_sentence)) > 0:
            # evaluate_and_show_attention(input_sentence, target_sentence)
            output_words, attentions = evaluate(input_sentence, pos)
            output_sentence = ' '.join(output_words)
            print('>', input_sentence)
            if target_sentence is not None:
                print('=', target_sentence)
            print('<', output_sentence)
            if (output_sentence == target_sentence):
                print('True')
                right_num += 1
            else:
                print('False')
    accuracy = right_num / length
    print(accuracy)

def evaluate_pairs_num(test_pairs,epoch):
    length = len(test_pairs)
    right_num = 0
    all_num = 0
    accuracy = 0.0
    for i in range(length):
        [input_sentence, target_sentence, pos] = test_pairs[i]
        if (len(input_sentence)) > 0:
            # evaluate_and_show_attention(input_sentence, target_sentence)
            output_words, attentions = evaluate(input_sentence, pos)
            if target_sentence is not None:
                target_words = target_sentence.split()
                all_num += len(target_words)
            
            for i in range(min(len(output_words), len(target_words))):
                if output_words[i] == target_words[i]:
                    right_num += 1
            

    #         output_sentence = ' '.join(output_words)
    #         print('>', input_sentence)
    #         if target_sentence is not None:
    #             print('=', target_sentence)
    #         print('<', output_sentence)
    #         if (output_sentence == target_sentence):
    #             print('True')
    #         else:
    #             print('False')
    # print('right_num=',right_num)
    # print('all_num=',all_num)
    accuracy = right_num / all_num
    ACC_seq.append(accuracy)
    
    print('test data accuracy = ', accuracy)

def evaluate_pairs_num_me(test_pairs,epoch):
    length = len(test_pairs)
    right_num = 0
    all_num = 0
    accuracy = 0.0
    for i in range(length):
        
        [input_sentence, target_sentence, pos] = test_pairs[i]
        if (len(input_sentence)) > 0:
            # evaluate_and_show_attention(input_sentence, target_sentence)
            output_words, attentions = evaluate(input_sentence, pos)
            if target_sentence is not None:
                target_words = target_sentence.split()
                for w in target_words:
                    if w.isdigit() and len(w) == 10:
                        all_num = all_num + 1
                #all_num += len(target_words)
            
            for i in range(min(len(output_words), len(target_words))):
                if output_words[i] == target_words[i] and output_words[i].isdigit() and len(output_words[i]) == 10:
                    right_num += 1
            

    accuracy = right_num / all_num
    ACC_sense.append(accuracy)
        
    print('test data accuracy for sense = ', accuracy)

def evaluate_pairs_num_me_is_there(test_pairs,epoch):   # not needed right now
    length = len(test_pairs)
    right_num = 0
    all_num = 0
    accuracy = 0.0
    for i in range(length):
        
        [input_sentence, target_sentence, pos] = test_pairs[i]
        if (len(input_sentence)) > 0:
            target_senses = []
            pred_senses = []
            # evaluate_and_show_attention(input_sentence, target_sentence)
            output_words, attentions = evaluate(input_sentence, pos)
            if target_sentence is not None:
                target_words = target_sentence.split()
                for w in target_words:
                    if w.isdigit() and len(w) == 10:
                        all_num = all_num + 1
                        target_senses.append(w)
                #all_num += len(target_words)
                for w in output_words:
                    if w.isdigit() and len(w) == 10:
                        pred_senses.append(w)
                #print("Debug:")
                #print("target senses:",target_senses)
                #print("out_senses:",pred_senses)
                for i in range(min(len(target_senses),len(pred_senses))):
                    if target_senses[i] == pred_senses[i]:
                        right_num += 1
            
    
    accuracy = right_num / all_num
    ACC_sense_updated.append(accuracy)
    
    print('test data accuracy for sense(updated) = ', accuracy)

F1_score = []



def vocab_for_F1():   # returns a dict of indexing for F1 score
    word2index_f1 = {}

    keys_input = input_lang.word2index.keys()
    set_vocab  = set()
    
    for k in keys_input:
        set_vocab.add(k)
    
    set_vocab.add('PAD')
    set_vocab.add('SOS')
    set_vocab.add('EOS')
    
    keys_output = output_lang.word2index.keys()
    for k in keys_output:
        set_vocab.add(k)
    
    i = 0
    set_vocab = list(set_vocab)
    for x in set_vocab:
        word2index_f1[x] = i
        i = i + 1
    return word2index_f1


def cal_culate_F1_score(test_pairs):
    y_true = []
    y_pred = []
    length = len(test_pairs)
    
    word2idex = vocab_for_F1()
    
    for i in range(length):
        [input_sentence, target_sentence,pos] = test_pairs[i]
        if (len(input_sentence)) > 0:
            # evaluate_and_show_attention(input_sentence, target_sentence)
            output_words, attentions = evaluate(input_sentence,pos)
            if target_sentence is not None:
                target_words = target_sentence.split()
                
                for i in range(min(len(output_words), len(target_words))):
                    y_true.append(word2idex[target_words[i]])
                    y_pred.append(word2idex[output_words[i]])
        
    from sklearn.metrics import f1_score
    
    f1_score = f1_score(y_true,y_pred,average='micro')
    #f1_score_m = f1_score(y_true,y_pred,average='micro')
    
    
    #accuracy = right_num / all_num
    print('F1-score(micro): ', f1_score)
    #print('F1-score(micro): ', f1_score_m)
    return f1_score


best_F1 = -1

def optimized_evaluate(test_pairs,check):
    #acc
    global best_F1
    print("best F1:   " , best_F1)
    length = len(test_pairs)
    right_num = 0
    all_num = 0
    accuracy = 0.0
    
    #F1 score
    
    y_true = []
    y_pred = []
    pos_true = []
    length = len(test_pairs)
    
    word2idex = vocab_for_F1()
    
    if check == 0:
        indexes = np.random.choice(length, length, replace  = False)
    else:
        indexes = np.random.choice(length, length, replace = False)
    
    for j in range(len(indexes)):
        print (j)
        dummy_y =[]
        dummy_x =[]
        if j % 500 == 0:
            print("evaluating this one  : ", j)
#        i = indexes[j]
        i = j;
        
        [input_sentence, target_sentence, pos] = test_pairs[i]
        if (len(input_sentence)) > 0:
            # evaluate_and_show_attention(input_sentence, target_sentence)
            output_words, attentions = evaluate(input_sentence, pos)
            if target_sentence is not None:
                target_words = target_sentence.split()
                true_pos = pos.split() 
                all_num += len(target_words)
            
            for i in range(min(len(output_words), len(target_words))):
                y_true.append(word2idex[target_words[i]])
                y_pred.append(word2idex[output_words[i]])
                pos_true.append(input_lang.word2index[true_pos[i]])
                
                dummy_y.append(output_words[i])
                dummy_x.append(target_words[i])

                if output_words[i] == target_words[i]:
                    right_num += 1


        import pickle
        with open('TRUE_PRED_POS.pkl', "wb") as f:
            pickle.dump([y_true, y_pred, pos_true], f)
            
    from sklearn.metrics import f1_score
    accuracy = right_num / all_num
    f1_score = f1_score(y_true,y_pred,average='micro')
    print('F1-score(micro): ', f1_score)
    print('test data accuracy = ', accuracy)
    ACC_seq.append(accuracy)
    F1_score.append(f1_score)
    if best_F1 < f1_score:
        torch.save(encoder.state_dict(),'best_encoder_conv_pos')
        torch.save(decoder.state_dict(),'best_decoder_conv_pos')
        best_F1 = f1_score
    return accuracy, f1_score


# Begin!
ecs = []
dcs = []
eca = 0
dca = 0



for i in range(len(pairs)):
    pairs[i].append(pairs_pos[i][0])
    
for i in range(len(test_pairs)):
    test_pairs[i].append(test_pairs_pos[i][0])
    
#f = open("result1.pkl","wb")
Ws = []  


while epoch < n_epochs:
    print("...", epoch)
    epoch += 1
    
    # Get training data for this cycle
    input_batches, input_lengths, target_batches, target_lengths, pos_batches, pos_lengths = random_batch(batch_size, pairs)
    
#    , input_lengths_pos, _ , _ = random_batch(batch_size, pairs_pos)

    # Run the train function
    loss, ec, dc,att = train(
        input_batches, input_lengths, target_batches, target_lengths, pos_batches, pos_lengths,
        encoder, decoder,
        encoder_optimizer, decoder_optimizer, criterion
    )

    # Keep track of loss
    print_loss_total += loss
    plot_loss_total += loss
    eca += ec
    dca += dc
    

    
    if epoch % print_every == 0:
        print_loss_avg = print_loss_total / print_every
        print_loss_total = 0
        print_summary = '%s (%d %d%%) %.4f' % (time_since(start, epoch / n_epochs), epoch, epoch / n_epochs * 100, print_loss_avg)
        print(print_summary)
        # evaluate_pairs_num(test_pairs)
        
    if epoch % evaluate_every == 0:
        print("current W1:",decoder.W1.data,"current W2:",decoder.W2.data, "current W3:",decoder.W3.data)
        evaluate_randomly()
#        evaluate_pairs_num(test_pairs,epoch)
        #evaluate_pairs_num_me(test_pairs,epoch)
        #evaluate_pairs_num_me_is_there(test_pairs,epoch)
        
#        F1_score.append(cal_culate_F1_score(test_pairs))
        
        optimized_evaluate(test_pairs,0)
        Ws.append((decoder.W1.data.cpu().numpy(),decoder.W2.data.cpu().numpy()))
        with open("result_conv_pos.pkl","wb") as f: #change the name of the file to result_pos_conv.pkl
            
            pickle.dump([F1_score,ACC_seq,ACC_sense,Ws],f)
        
        decoder_att.append(att)
    if epoch % plot_every == 0:
        plot_loss_avg = plot_loss_total / plot_every
        plot_losses.append(plot_loss_avg)
        plot_loss_total = 0
        
        # TODO: Running average helper
        ecs.append(eca / plot_every)
        dcs.append(dca / plot_every)
        ecs_win = 'encoder grad (%s)' % hostname
        dcs_win = 'decoder grad (%s)' % hostname
        # vis.line(np.array(ecs), win=ecs_win, opts={'title': ecs_win})
        # vis.line(np.array(dcs), win=dcs_win, opts={'title': dcs_win})
        eca = 0
        dca = 0
        
        
encoder.load_state_dict(torch.load('best_encoder_conv_pos'))
decoder.load_state_dict(torch.load('best_decoder_conv_pos'))
optimized_evaluate(test_pairs, 1)

with open("vocab.pkl","wb") as f:
    pickle.dump([input_lang.word2index, input_lang.index2word],f)


# test_data = "/home/yi/Documents/rnn/test_10.txt"
# input_lang0, output_lang0, test_pairs = prepare_data('test_w', 'test_s', test_data, False)       
# evaluate_pairs(test_pairs)
#evaluate_pairs_num(test_pairs,epoch)
#evaluate_pairs_num_me(test_pairs,epoch)
#evaluate_pairs_num_me_is_there(test_pairs,epoch)
#F1_score.append(cal_culate_F1_score(test_pairs))
