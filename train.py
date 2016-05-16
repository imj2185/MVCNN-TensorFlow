import numpy as np
import os,sys,inspect
import tensorflow as tf
import time
from datetime import datetime
import os
import hickle as hkl
import os.path as osp
from glob import glob

from input import Dataset


currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.append(parentdir)
import model

TRAIN_HKL = './data/view/hkl/train.hkl'
LISTS_DIR = './data/view/list/train/'

FLAGS = tf.app.flags.FLAGS
tf.app.flags.DEFINE_string('train_dir', '/tmp3/weitang114/MVCNN-TF/tmp/',
                           """Directory where to write event logs """
                           """and checkpoint.""")
tf.app.flags.DEFINE_integer('max_steps', 1000000,
                            """Number of batches to run.""")
tf.app.flags.DEFINE_boolean('log_device_placement', False,
                            """Whether to log device placement.""")
tf.app.flags.DEFINE_string('weights', '', 
                            """finetune with a pretrained model""")
tf.app.flags.DEFINE_string('n_views', 12, 
                            """Number of views rendered from a mesh.""")

# Constants describing the training process.
MOVING_AVERAGE_DECAY = 0.9999     # The decay to use for the moving average.
NUM_EPOCHS_PER_DECAY = 20.0      # Epochs after which learning rate decays.
LEARNING_RATE_DECAY_FACTOR = 0.05  # Learning rate decay factor.

np.set_printoptions(precision=3)



def train(dataset, ckptfile=''):
    print 'train() called'
    is_finetune = bool(ckptfile)
    V = FLAGS.n_views
    batch_size = FLAGS.batch_size

    dataset.shuffle()
    dataset.split_val()
    data_size = dataset.size()


    with tf.Graph().as_default():
        startstep = 0 if not is_finetune else int(ckptfile.split('-')[-1])
        global_step = tf.Variable(startstep, trainable=False)
         
        
        view_ = tf.placeholder('float32', shape=(batch_size, V, 227, 227, 3), name='im0')
        y_ = tf.placeholder('int64', shape=(batch_size), name='y')

        fc8 = model.inference_multiview(view_)
        loss = model.loss(fc8, y_)

        train_op = model.train(loss, global_step, data_size)
        prediction = model.classify(fc8)
        accuracy = model.accuracy(prediction, y_)

        # build the summary operation based on the F colection of Summaries
        summary_op = tf.merge_all_summaries()


        # must be after merge_all_summaries
        validation_loss = tf.placeholder('float32', shape=(), name='validation_loss')
        validation_summary = tf.scalar_summary('validation_loss', validation_loss)

        saver = tf.train.Saver(tf.all_variables(), max_to_keep=1000)

        init_op = tf.initialize_all_variables()
        sess = tf.Session(config=tf.ConfigProto(log_device_placement=FLAGS.log_device_placement))
        
        if not is_finetune:
            sess.run(init_op)
            print 'init_op done'
        else:
            saver.restore(sess, ckptfile)
            print 'restore variables done'

        summary_writer = tf.train.SummaryWriter(FLAGS.train_dir,
                                                graph_def=sess.graph_def) 

        step = startstep
        for batch_x, batch_y in dataset.batches(batch_size):
            if step >= FLAGS.max_steps:
                break
            step += 1

            start_time = time.time()
            feed_dict = {view_: batch_x,
                         y_ : batch_y}

            # print batch_x, batch_y
            # batch_fc4 = sess.run(fc4, feed_dict=feed_dict)
            # print list(batch_fc4[10])


            """,batch_fc5,  batch_fc4, batch_pool3, batch_pool2, batch_pool1 """

            _, pred, loss_value = sess.run(
                    [train_op, prediction,  loss,],
                    feed_dict=feed_dict)

            duration = time.time() - start_time

            assert not np.isnan(loss_value), 'Model diverged with loss = NaN'

            if step % 10 == 0:
                sec_per_batch = float(duration)
                print '%s: step %d, loss=%.2f (%.1f examples/sec; %.3f sec/batch)' \
                     % (datetime.now(), step, loss_value,
                                FLAGS.batch_size/duration, sec_per_batch)

                    
            # val
            if step % 100 == 0:# and step > 0:
                n_val = val_x.shape[0]
                val_losses = []
                predictions = np.array([])
                for val_step in xrange(n_val/FLAGS.batch_size):
                    val_batch_x, val_batch_y = fetch_batch(val_x, val_y, val_step, FLAGS.batch_size)
                    val_feed_dict = {im_: val_batch_x,
                                     y_  : val_batch_y}
                    val_loss, pred = sess.run([loss, prediction], feed_dict=val_feed_dict)
                    # print val_batch_y[:20]
                    # print pred[:20]
                    val_losses.append(val_loss)
                    predictions = np.hstack((predictions, pred))

                val_loss = np.mean(val_losses)
                acc = sess.run(accuracy, feed_dict={prediction: np.array(predictions), y_:val_y[:predictions.size]})
                print '%s: step %d, validation loss=%.2f, acc=%f' %\
                        (datetime.now(), step, val_loss, acc*100.)

                # validation summary
                val_summ = sess.run(validation_summary, 
                                    feed_dict={validation_loss: val_loss})
                summary_writer.add_summary(val_summ, step)
                summary_writer.flush()


            if step % 20 == 0:
                # print 'running fucking summary'
                summary_str = sess.run(summary_op, feed_dict=feed_dict)
                summary_writer.add_summary(summary_str, step)
                summary_writer.flush()

            if step % 200  == 0 or (step+1) == FLAGS.max_steps \
                    and step > startstep:
                checkpoint_path = os.path.join(FLAGS.train_dir, 'model.ckpt')
                saver.save(sess, checkpoint_path, global_step=step)



def main(argv):
    st = time.time() 
    print 'start loading data'

    listfiles = read_lists()
    dataset = Dataset(listfiles, subtract_mean=True, V=12)

    print 'done loading data, time=', time.time() - st

    FLAGS.batch_size = 32

    train(dataset, FLAGS.weights)


def read_lists():
    classes = np.loadtxt('./data/classes.txt', dtype=str)
    lists = []
    for c in classes:
        lists.extend(glob(osp.join(LISTS_DIR, c, '*.txt')))
    return lists


if __name__ == '__main__':
    main(sys.argv)

