import tensorflow as tf

from tensorflow.keras.models import save_model # can't resolve the import, could it be from keras.models import save_model?
from tensorflow.keras.layers import LSTM, Dense 
from tensorflow.keras.models import Sequential
from sklearn.model_selection import train_test_split
import itertools
import joblib
from datetime import datetime
import pandas as pd
import numpy as np
import time
from src.AI_fun import (warnings, dataset_name, resample_co, time_steps, future_points, sequences, 
                        validations, round_up, modeler_mode, loc_folder,Import_AI,crypto,interval,standardize_and_normalize, normalize,
                        prepare_input_target_data, create_separate_scalers, arr_list, layers,epochs, batch_size,dropout, 
                        learning_rate, act_input, act_output,test_size,create_model, verbose, model_name, scalers_name, model_reset)
# Disable all warnings
warnings.filterwarnings('ignore')

'''
                                       ---------- RNN LSTM Modeler -----------

This tool will train an LSTM RNN based on the hyperparameters and combination defined by the tuner. 
This modeler can be runned in two different modes defined by the modeler_mode value in AI_Config. 
If the modeler runs in parallel with the trader the modeler will share the dataset file with the trader program to 
assure that is using the latest information to model so it will look for this dataset first and wait until it has enough 
length to be able to model. Once it finds a better predictive model for the price movement it will update the model. The value model_reset defines a number of 
seconds after which the accuracy score will be reset so that a more updated model can be train.
If the modeler runs 'solo' instead of waiting it will download it's own dataset and train the model based on that.
'''

def modeler(dataset_name = dataset_name):
    dataset_name_2 = 'm_' + dataset_name
    resample_size = f'{str(resample_co)}s'
    idx = (time_steps + future_points * sequences) * validations
    w0 = 28 * future_points
    limi = w0 + idx
    limit_len = limi * resample_co
    since = round_up(limit_len / 3600,
                     2)  # Since must be expressed in hours if limit len is expressed in seconds  we divide by 3600.
    best_score = 0
    best_combination = None
    last_reset = datetime.now()
    while True:
        if modeler_mode == 'parallel':
            while True:
                try:
                    print(f'Retrieving dataset: {dataset_name}')
                    dataset = pd.read_csv(f'{loc_folder}{dataset_name}', index_col=['datetime'], parse_dates=True).fillna(method='ffill')
                except:
                    print(f'Shared dataset could not be found. Retrying in 60 seconds...')
                    time.sleep(60)
                    continue
                break
        elif modeler_mode == 'solo':
            dataset_name = dataset_name_2
            print(f'Downloading dataset: {dataset_name}')
            Import_AI(name=dataset_name, cryptos=crypto, sample_freq=interval, since=since, future_points=future_points,
            resample_size=resample_size)
            dataset = pd.read_csv(f'{loc_folder}{dataset_name}', index_col=['datetime'], parse_dates=True).fillna(method='ffill')
        else:
            print('modeler_mode variable is not correctly defined. It should set either as parallel or solo')
            exit()
        if len(dataset) < limi and modeler_mode == 'solo':
            print('Dataset is not long enough, exiting...')
            exit()
        elif len(dataset) >= limi:
            print('Starting modeling...')
            start_t = datetime.now()
            print(f'Current Datetime:{start_t}')
            dataset = dataset.resample(resample_size).agg(
                {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum', 'so': 'last',
                'pvo': 'last', 'ema': 'last', 'rsi': 'last', 'srsi': 'last', 'cci': 'last', 'psar': 'last',
                'vwap': 'last'}).fillna(
                method='ffill')
            dataset['Return'] = dataset.close.pct_change(future_points).shift(-future_points)
            feat_num = len(dataset.columns) - 1
            dataset = dataset[-idx:]
            dataset.dropna(inplace=True)
            # Separate columns based on types
            price_columns = ['open', 'close', 'high', 'low']
            volume_column = ['volume']
            indicator_columns = ['so', 'pvo', 'ema', 'rsi', 'srsi', 'cci', 'psar', 'vwap']

            # Prepare the data
            input_data, target_data = prepare_input_target_data(dataset, feat_num)

            # Create separate scalers for each category of features
            open_scaler, high_scaler, low_scaler, close_scaler, volume_scaler, so_scaler, pvo_scaler, ema_scaler, rsi_scaler, srsi_scaler, cci_scaler, psar_scaler, vwap_scaler, target_scaler = create_separate_scalers()

            # Standardize and normalize the price data
            open_data = standardize_and_normalize(input_data, scaler=open_scaler, data_axis=0)
            high_data = standardize_and_normalize(input_data, scaler=high_scaler, data_axis=1)
            low_data = standardize_and_normalize(input_data, scaler=low_scaler, data_axis=2)
            close_data = standardize_and_normalize(input_data, scaler=close_scaler, data_axis=3)

            # Standardize and normalize EMA and PSAR
            ema_data = standardize_and_normalize(input_data, ema_scaler, data_axis=3, p_len=4)
            psar_data = standardize_and_normalize(input_data, psar_scaler, data_axis=7, p_len=4)
            vwap_data = standardize_and_normalize(input_data, vwap_scaler, data_axis=8, p_len=4)

            # Normalize SO, WI, PVO, SRSI & CCI
            so_data = normalize(input_data, so_scaler, data_axis=1, p_len=4)
            pvo_data = normalize(input_data, pvo_scaler, data_axis=2, p_len=4)
            rsi_data = normalize(input_data, rsi_scaler, data_axis=4, p_len=4)
            srsi_data = normalize(input_data, srsi_scaler, data_axis=5, p_len=4)
            cci_data = normalize(input_data, cci_scaler, data_axis=6, p_len=4)

            # Standardize the volume data
            volume_data = normalize(input_data, volume_scaler, data_axis=4)

            # Normalize the output data
            target_data = target_scaler.fit_transform(target_data.reshape(-1, 1)).reshape(target_data.shape)

            # List of arrays to choose from
            arr_dic = {'so': so_data, 'pvo': pvo_data, 'ema': ema_data, 'rsi': rsi_data,
                    'srsi': srsi_data, 'cci': cci_data, 'psar': psar_data, 'vwap': vwap_data}
            array = [arr_dic[arr_list[i]] for i in range(len(arr_list))]
            acc_mean = 0
            loss_mean = 0
            input_data = np.concatenate((open_data, high_data, low_data, close_data, volume_data, *array), axis=2)
            combination_indexes = []
            print(f'Combination Indexes: {arr_list}')

            # Create and fit the LSTM model with the specified hyperparameters
            print(f'Layers: {layers} Epochs: {epochs} Batch Size: {batch_size} Dropout Rate: {dropout} Learning Rate: {learning_rate} Input Act. Func: {act_input} Output Act. Func: {act_output}')
            for x in range(validations):
                ix = int(len(input_data) / validations) * x
                fx = ix + int(len(input_data) / validations)
                input_d = input_data[ix:fx, :, :]
                target_d = target_data[ix:fx]
                input_train, input_test, target_train, target_test = train_test_split(input_d, target_d, test_size=test_size, shuffle=False)
                # Create Model
                model = create_model(input_d, num_lstm_units=layers, dropout_rate=dropout, learning_rate=learning_rate,
                                    activation_input=act_input,
                                    activation_output=act_output)
                # Fit the model
                model.fit(input_train, target_train, epochs=epochs, batch_size=batch_size, verbose=verbose)
                # Evaluate the model on the test set
                loss, accuracy = model.evaluate(input_test, target_test, verbose=verbose)
                predictions = model.predict(input_test)
                predictions = target_scaler.inverse_transform(predictions.reshape(-1, 1))
                predictions = np.where(predictions >= 0, 1, 0)  # Convert probabilities to binary predictions
                target_test = target_scaler.inverse_transform(target_test.reshape(-1, 1))
                target_test = np.where(target_test >= 0, 1, 0)  # Convert probabilities to binary predictions
                accuracy = np.mean(predictions == target_test)  # Calculate accuracy
                print(f'Accuracy: {accuracy:.2f}')
                acc_mean += accuracy / validations
                loss_mean += loss / validations
            # Check if the current combination is better than the previous best
            print(f'Avg. Accuracy: {acc_mean:.2f}')
            print(f'Avg. Loss: {loss_mean:.2f}')
            # Check if the current combination is better than the previous best
            if acc_mean > best_score:
                best_score = acc_mean
                best_combination = array
                best_model = model
                best_combination_indexes = combination_indexes
                # Save model and Scalers
                scalers = {
                    'open_scaler': open_scaler,
                    'high_scaler': high_scaler,
                    'low_scaler': low_scaler,
                    'close_scaler': close_scaler,
                    'volume_scaler': volume_scaler,
                    'target_scaler': target_scaler,
                    'so_scaler': so_scaler,
                    'pvo_scaler': pvo_scaler,
                    'ema_scaler': ema_scaler,
                    'rsi_scaler': rsi_scaler,
                    'srsi_scaler': srsi_scaler,
                    'cci_scaler': cci_scaler,
                    'psar_scaler': psar_scaler,
                    'vwap_scaler': vwap_scaler,
                }
                print(f'Best accuracy so far:{best_score:.4f}')
                print('Saving Model...')
                save_model(best_model,  f'{loc_folder}{model_name}')  # Saves model to be used by the Trader
                joblib.dump(scalers,  f'{loc_folder}{scalers_name}')  # Saves scalers to be used by the Trader
                elapsed_time = (datetime.now() - last_reset).total_seconds()
                # Check if it's time to reset the variable
                if elapsed_time > model_reset and modeler_mode == 'parallel':
                    best_score = 0
                    last_reset = datetime.now()
                    print(f'Modeling duration: {datetime.now() - start_t}')
                elif modeler_mode == 'solo':
                    print(f'Modeling duration: {datetime.now() - start_t}')
                    exit()
        else:
            print('Dataset is not long enough yet for modeling')
            time.sleep(60)
            continue
        time.sleep(30)

