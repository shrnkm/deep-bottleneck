import os
import pickle

import pandas as pd
import numpy as np
from tensorflow.contrib.keras import backend as K

from iclr_wrap_up import kde
from iclr_wrap_up import simplebinmi
from iclr_wrap_up import utils

def load(training_data, test_data, epochs, architecture_name, full_mi, activation_fn, infoplane_measure):
    estimator = MutualInformationEstimator(training_data, test_data, epochs,
                                           architecture_name, full_mi, activation_fn, infoplane_measure)
    return estimator


class MutualInformationEstimator:

    def __init__(self, training_data, test_data, epochs, architecture_name, full_mi, activation_fn, infoplane_measure):
        self.training_data = training_data
        self.test_data = test_data
        self.epochs = epochs
        self.architecture_name = architecture_name
        self.full_mi = full_mi
        self.activation_fn = activation_fn
        self.infoplane_measure = infoplane_measure

    def compute_mi(self):

        compute_lower_bounds = False

        DO_LOWER = (self.infoplane_measure == 'lower')  # Whether to compute lower bounds also
        DO_BINNED = (self.infoplane_measure == 'bin')  # Whether to compute MI estimates based on binning

        # Functions to return upper and lower bounds on entropy of layer activity
        noise_variance = 1e-3  # Added Gaussian noise variance
        binsize = 0.07  # size of bins for binning method

        Klayer_activity = K.placeholder(ndim=2)  # Keras placeholder
        entropy_func_upper = K.function([Klayer_activity, ],
                                        [kde.entropy_estimator_kl(Klayer_activity, noise_variance), ])
        entropy_func_lower = K.function([Klayer_activity, ],
                                        [kde.entropy_estimator_bd(Klayer_activity, noise_variance), ])

        # nats to bits conversion factor
        nats2bits = 1.0 / np.log(2)

        # Save indexes of tests data for each of the output classes
        saved_labelixs = {}

        y = self.test_data.y
        Y = self.test_data.Y
        if self.full_mi:
            full = utils.construct_full_dataset(self.training_data, self.test_data)
            y = full.y
            Y = full.Y

        for i in range(self.training_data.nb_classes):
            saved_labelixs[i] = y == i

        labelprobs = np.mean(Y, axis=0)

        # Data structure used to store results
        measures = {}

        cur_dir = f'rawdata/{self.activation_fn}_{self.architecture_name}'
        if not os.path.exists(cur_dir):
            print("Directory %s not found" % cur_dir)

        # Load files saved during each epoch, and compute MI measures of the activity in that epoch
        print(f'*** Doing {cur_dir} ***')
        for epochfile in sorted(os.listdir(cur_dir)):
            if not epochfile.startswith('epoch'):
                continue

            fname = f'{cur_dir}/{epochfile}'
            with open(fname, 'rb') as f:
                d = pickle.load(f)

            epoch = d['epoch']

            if epoch > self.epochs:
                continue

            print("Doing", fname)

            num_layers = len(d['data']['activity_tst'])

            info_measures = ['MI_XM_upper', 'MI_YM_upper', 'MI_XM_lower', 'MI_YM_lower', 'MI_XM_bin',
                             'MI_YM_bin', 'H_M_upper', 'H_M_lower']

            current_epoch_data = pd.DataFrame(columns=info_measures, index=range(num_layers))

            for layer_index in range(num_layers):
                activity = d['data']['activity_tst'][layer_index]

                if self.infoplane_measure == "upper":
                    # Compute marginal entropies
                    h_upper = entropy_func_upper([activity, ])[0]

                    # Layer activity given input. This is simply the entropy of the Gaussian noise
                    hM_given_X = kde.kde_condentropy(activity, noise_variance)

                    # Compute conditional entropies of layer activity given output
                    hM_given_Y_upper = 0.
                    for i in range(self.training_data.nb_classes):
                        hcond_upper = entropy_func_upper([activity[saved_labelixs[i], :], ])[0]
                        hM_given_Y_upper += labelprobs[i] * hcond_upper

                    current_epoch_data['MI_XM_upper'][layer_index] = nats2bits * (h_upper - hM_given_X)
                    current_epoch_data['MI_YM_upper'][layer_index] = nats2bits * (h_upper - hM_given_Y_upper)
                    current_epoch_data['H_M_upper'][layer_index] = nats2bits * h_upper

                    pstr = 'upper: MI(X;M)=%0.3f, MI(Y;M)=%0.3f' % (
                        current_epoch_data['MI_XM_upper'][layer_index], current_epoch_data['MI_YM_upper'][layer_index])

                if self.infoplane_measure == "lower":

                    h_lower = entropy_func_lower([activity, ])[0]

                    hM_given_Y_lower = 0.

                    for i in range(self.training_data.nb_classes):
                        hcond_lower = entropy_func_lower([activity[saved_labelixs[i], :], ])[0]
                        hM_given_Y_lower += labelprobs[i] * hcond_lower

                    current_epoch_data['MI_XM_lower'][layer_index] = nats2bits * (h_lower - hM_given_X)
                    current_epoch_data['MI_YM_lower'][layer_index] = nats2bits * (h_lower - hM_given_Y_lower)
                    current_epoch_data['H_M_lower'][layer_index] = nats2bits * h_lower

                    pstr += ' | lower: MI(X;M)=%0.3f, MI(Y;M)=%0.3f' % (
                        current_epoch_data['MI_XM_lower'][layer_index], current_epoch_data['MI_YM_lower'][layer_index])

                if self.infoplane_measure == "bin":
                    binxm, binym = simplebinmi.bin_calc_information2(saved_labelixs, activity, binsize)
                    current_epoch_data['MI_XM_bin'][layer_index] = nats2bits * binxm
                    current_epoch_data['MI_YM_bin'][layer_index] = nats2bits * binym

                    pstr += ' | bin: MI(X;M)=%0.3f, MI(Y;M)=%0.3f' % (
                        current_epoch_data['MI_XM_bin'][layer_index], current_epoch_data['MI_YM_bin'][layer_index])

                print(f'- Layer {layer_index} {pstr}')

            measures[epoch] = current_epoch_data

        return measures
