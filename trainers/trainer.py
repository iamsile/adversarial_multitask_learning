import os
import sys
sys.path.append("..")
import yaml
import random
import numpy as np
import tensorflow as tf
from tensorflow.contrib import learn
from model.adversarial_model import Adversarial_Network
from utils.data_loader import load_data, batch_iter
from itertools import chain

with open("../config/config.yaml", "rb") as f:
    params = yaml.load(f)


class EVAL(object):
    """    
    This is a training without adversarial network    
    """

    def __init__(self, sequence_length):
        # load data first
        self.processor = learn.preprocessing.VocabularyProcessor.restore(
            "../temp/vocab")
        self.processor.max_document_length = sequence_length
        raw_data, raw_label = load_data("train")
        self.train_data = []
        self.train_label = []
        for rd, rl in zip(raw_data, raw_label):
            # for each task in data
            tmp_data = []
            tmp_label = []
            rd = list(self.processor.transform(rd))  # generator -> list
            for tmp_x, tmp_y in zip(rd, rl):
                tmp_x = tmp_x.tolist()
                if np.sum(tmp_x) != 0:
                    tmp_data.append(tmp_x)
                    tmp_label.append(tmp_y)
            self.train_data.append(tmp_data)
            self.train_label.append(tmp_label)
        del raw_data, raw_label
        print("load training data complete!")

        self.test_data = []
        self.test_label = []
        raw_data, raw_label = load_data("test")
        for rd, rl in zip(raw_data, raw_label):
            tmp_data = []
            tmp_label = []
            rd = list(self.processor.transform(rd))
            for tmp_x, tmp_y in zip(rd, rl):
                tmp_x = tmp_x.tolist()
                if np.sum(tmp_x) != 0:
                    tmp_data.append(tmp_x)
                    tmp_label.append(tmp_label)
            self.test_data.append(tmp_data)
            self.test_label.append(tmp_label)
        del raw_data, raw_label
        print("load test data complete!")
        self.embedding_matrix = self._embedding_matrix_initializer() if os.path.exists(
            "../data/glove.6B/glove.6B.{}d.txt".format(params["global"]["embedding_size"])) else None

        print("read from embedding_matrix complete!")

    def _embedding_matrix_initializer(self):
        """
        embedding layer initialization using pre-trained glovec
        """
        file_wv = "../data/glove.6B/glove.6B.{}d.txt".format(
            params["global"]["embedding_size"])
        wv = {}
        embedding_matrix = []

        with open(file_wv, 'r') as f:
            for line in f:
                line = line.split(' ')
                word = line[0]
                wv[word] = list(map(float, line[1:]))

        for idx in range(len(self.processor.vocabulary_)):
            word = self.processor.vocabulary_.reverse(idx)
            embedding_matrix.append(
                wv[word] if word in wv else np.random.normal(size=params["global"]["embedding_size"]))
        return embedding_matrix

    def process(self, learning_rate, batch_size, epochs, evaluate_every):
        """
        """
        embedding_matrix = list(chain.from_iterable(
            self.embedding_matrix)) if self.embedding_matrix else None
        with tf.Graph().as_default():
            instance = Adversarial_Network(
                sequence_length=params["global"]["sequence_length"],
                num_classes=params["global"]["num_classes"],
                embedding_size=params["global"]["embedding_size"],
                vocab_size=len(
                    self.processor.vocabulary_),
                embedding_matrix=embedding_matrix,
                static=params["global"]["static"],
                rnn_hidden_size=params["global"]["rnn_hidden_size"],
                shared_num_layers=params["shared_model"]["num_layers"],
                private_num_layers=params["private_model"]["num_layers"],
                dynamic=params["global"]["dynamic"],
                use_attention=params["global"]["use_attention"],
                attention_size=params["global"]["attention_size"],
                mlp_hidden_size=params["global"]["mlp_hidden_size"])

            global_step = tf.Variable(0, trainable=False)

            # adv_loss = instance.adv_loss  # TODO
            diff_loss = instance.diff_loss
            task_loss = instance.task_loss

            # discriminator_accuracy = instance.discriminator_accuracy
            task_accuracy = instance.task_accuracy

            # discriminator_optimizer = tf.train.AdamOptimizer(learning_rate)
            task_optimizer = tf.train.AdamOptimizer(learning_rate)
            # shared_optimizer = tf.train.AdamOptimizer(learning_rate)

            # discriminator_vars = tf.get_collection(
            #     tf.GraphKeys.TRAINABLE_VARIABLES, scope="discriminator")
            # shared_vars = tf.get_collection(
            #     tf.GraphKeys.TRAINABLE_VARIABLES, scope="shared")

            task_train_op = task_optimizer.minimize(
                task_loss + 0.0001 * diff_loss, global_step=global_step)
            # discriminator_train_op = discriminator_optimizer.minimize(
            #     adv_loss, var_list=discriminator_vars, global_step=global_step)
            # shared_train_op = shared_optimizer.minimize(
            #     -1 * adv_loss, var_list=shared_vars, global_step=global_step) # No varibales to optimize
            init = tf.global_variables_initializer()

            with tf.Session() as sess:
                sess.run(init)

                def train_step(task, x_batch, y_batch):
                    feed_dict = {
                        instance.task: task,
                        instance.input_x: x_batch,
                        instance.input_y: y_batch
                    }
                    step, _, diff_loss_, task_loss_, task_acc_ = sess.run(
                        [
                            global_step,
                            task_train_op,
                            diff_loss,
                            task_loss,
                            task_accuracy
                        ], feed_dict=feed_dict
                    )
                    return step, diff_loss_, task_loss_, task_acc_

                # def dev_step(task, x_batch, y_batch):
                #     feed_dict = {
                #         instance.task: task,
                #         instance.input_x: x_batch,
                #         instance.input_y: y_batch
                #     }
                #     step, diff_loss_, adv_loss_, task_loss_, dis_acc_, task_acc_ = sess.run(
                #         [
                #             global_step,
                #             diff_loss,
                #             adv_loss,
                #             task_loss,
                #             discriminator_accuracy,
                #             task_accuracy
                #         ], feed_dict=feed_dict
                #     )
                #     return step, diff_loss_, adv_loss_, task_loss_, dis_acc_, task_acc_

                for task, batch in batch_iter(self.train_data, self.train_label, batch_size, epochs, shuffle=False):
                    # print("graph loaded, training commence")
                    x_batch, y_batch = zip(*batch)
                    # diffloss = sess.run(instance.diff_loss, feed_dict={instance.task: task, instance.input_x: x_batch, instance.input_y: y_batch})
                    # print(diffloss)
                    current_step, diff_loss_, task_loss_, task_acc_ = train_step(
                        task, x_batch, y_batch)

                    # print("step: {}, adversarial loss: {:.5f}, task loss: {:.5f}, discriminator accuracy: {:.2f}, \
                    # task accuracy: {:.2f}".format(current_step,
                    #                               adv_loss_,
                    #                               task_loss_,
                    #                               dis_acc_,
                    #                               task_acc_))
                    print("step: {}, task loss: {:.5f}, task acc: {:.2f}".format(
                        current_step, task_loss_, task_acc_))
                    if current_step % evaluate_every == 0:
                        """
                        test transfer effect
                        """
                        pass
                    pass


if __name__ == "__main__":
    eval = EVAL(params["global"]["sequence_length"])
    eval.process(
        learning_rate=params["global"]["learning_rate"],
        batch_size=params["global"]["batch_size"],
        epochs=params["global"]["epochs"],
        evaluate_every=100
    )
