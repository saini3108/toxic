import sys, os, re, csv, codecs, numpy as np, pandas as pd
np.random.seed(32)

from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score

import logging

from keras.models import Model, load_model
from keras.layers import Input, Dense, Embedding, SpatialDropout1D, concatenate, Dropout, Activation, Conv1D
from keras.layers import MaxPooling1D, GlobalMaxPool1D, MaxPooling1D, Add, Flatten
from keras.layers import GRU, Bidirectional, GlobalAveragePooling1D, GlobalMaxPooling1D, BatchNormalization, Conv1D
from keras.preprocessing import text, sequence
from keras.callbacks import Callback, EarlyStopping, ModelCheckpoint, LearningRateScheduler
from keras.optimizers import Adam, RMSprop

from keras import initializers, regularizers, constraints, optimizers, layers, callbacks
from keras import backend as K
from keras.engine import InputSpec, Layer

import warnings
warnings.filterwarnings('ignore')

import os
os.environ['OMP_NUM_THREADS'] = '4'

import time
start_time = time.time()

num_cpu = 4
max_features = 100000
maxlen = 200
embed_size = 300

EMBEDDING_FILE = '../input/glove840b300dtxt/glove.840B.300d.txt'

train = pd.read_csv('../input/jigsaw-toxic-comment-classification-challenge/train.csv')
test = pd.read_csv('../input/jigsaw-toxic-comment-classification-challenge/test.csv')
submission = pd.read_csv('../input/jigsaw-toxic-comment-classification-challenge/sample_submission.csv')


X_train = train["comment_text"].fillna("fillna").values
y_train = train[["toxic", "severe_toxic", "obscene", "threat", "insult", "identity_hate"]].values
X_test = test["comment_text"].fillna("fillna").values

tokenizer = text.Tokenizer(num_words=max_features, lower = True)
tokenizer.fit_on_texts(list(X_train) + list(X_test))
X_train = tokenizer.texts_to_sequences(X_train)
X_test = tokenizer.texts_to_sequences(X_test)
x_train = sequence.pad_sequences(X_train, maxlen=maxlen)
x_test = sequence.pad_sequences(X_test, maxlen=maxlen)

def get_coefs(row):
    row = row.strip().split()
    word, arr = " ".join(row[:-embed_size]), row[-embed_size:]
    return word, np.asarray(arr, dtype='float32')

embeddings_index = dict(get_coefs(row) for row in open(EMBEDDING_FILE))

all_embs = np.stack(embeddings_index.values())
emb_mean, emb_std = all_embs.mean(), all_embs.std()

word_index = tokenizer.word_index
nb_words = min(max_features, len(word_index))
embedding_matrix = np.random.normal(emb_mean, emb_std, (nb_words, embed_size))
for word, i in word_index.items():
    if i >= max_features: continue
    embedding_vector = embeddings_index.get(word)
    if embedding_vector is not None: embedding_matrix[i] = embedding_vector


X_tra, X_val, y_tra, y_val = train_test_split(x_train, y_train, train_size=0.95, random_state=233)

class RocAucEvaluation(Callback):
    def __init__(self, validation_data=(), interval=1):
        super(Callback, self).__init__()

        self.interval = interval
        self.X_val, self.y_val = validation_data

    def on_epoch_end(self, epoch, logs={}):
        if epoch % self.interval == 0:
            y_pred = self.model.predict(self.X_val, verbose=1)
            score = roc_auc_score(self.y_val, y_pred)
            print("\n ROC-AUC - epoch: %d - score: %.6f \n" % (epoch+1, score))


file_path = "best_model.hdf5"
check_point = ModelCheckpoint(file_path, monitor = "val_loss", verbose = 1,
                              save_best_only = True, mode = "min")

RocAuc = RocAucEvaluation(validation_data=(X_val, y_val), interval=1)
early_stop = EarlyStopping(monitor = "val_loss", mode = "min", patience = 5)



def get_model(lr = 0.0, lr_d = 0.0, units = 0, dr = 0.0, batch_size = 128,epochs = 4):
    inp = Input(shape=(maxlen, ))
    x = Embedding(max_features, embed_size, weights=[embedding_matrix], trainable = False)(inp)
    x = SpatialDropout1D(dr)(x)
    x = Bidirectional(GRU(units, return_sequences=True))(x)
    x = Conv1D(64, kernel_size = 2, padding = "valid", kernel_initializer = "he_uniform")(x)

    avg_pool = GlobalAveragePooling1D()(x)
    max_pool = GlobalMaxPooling1D()(x)
    conc = concatenate([avg_pool, max_pool])
    outp = Dense(6, activation="sigmoid")(conc)
    model = Model(inputs=inp, outputs=outp)
    model.compile(loss='binary_crossentropy',
                  optimizer = Adam(lr = lr, decay = lr_d),
                  metrics=['accuracy'])
    hist = model.fit(X_tra, y_tra, batch_size=batch_size, epochs=epochs, validation_data=(X_val, y_val),
                 callbacks=[RocAuc,check_point, early_stop], verbose=2)
    model = load_model(file_path)
    return model

model = get_model(lr = 1e-3, lr_d = 0, units = 80, dr = 0.2, batch_size = 32,epochs = 4)
y_pred = model.predict(x_test, batch_size=1024, verbose = 1)

submission[["toxic", "severe_toxic", "obscene", "threat", "insult", "identity_hate"]] = y_pred
submission.to_csv('submission.csv', index=False)

print("[{}] Completed!".format(time.time() - start_time))