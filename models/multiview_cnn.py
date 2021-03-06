import numpy as np

from sklearn.metrics import confusion_matrix

from keras.applications.vgg16 import VGG16
from keras.callbacks import CSVLogger, ModelCheckpoint, ReduceLROnPlateau
from keras.layers import Dense, Flatten, Input, Dropout
from keras.optimizers import SGD
from keras.models import Model

from geometry_processing.globals import (TRAIN_DIR, VALID_DIR, MODEL_WEIGHTS,
        LOG_FILE, IMAGE_SIZE, NUM_CLASSES, IMAGE_MEAN, IMAGE_STD)
from geometry_processing.utils.helpers import (get_data, samplewise_normalize,
        load_weights)


# Set to 2 on supercomputer during training.
VERBOSE = 1


def train(model, save_to=''):
    # Center and normalize each sample.
    normalize = samplewise_normalize(IMAGE_MEAN, IMAGE_STD)

    # Get streaming data.
    train_generator = get_data(TRAIN_DIR, preprocess=normalize)
    valid_generator = get_data(VALID_DIR, preprocess=normalize)

    print('%d training samples.' % train_generator.n)
    print('%d validation samples.' % valid_generator.n)

    model.compile(loss='categorical_crossentropy',
                  optimizer=SGD(lr=1e-3, momentum=0.9),
                  metrics=['accuracy'])

    callbacks = list()

    callbacks.append(CSVLogger(LOG_FILE))
    callbacks.append(ReduceLROnPlateau(monitor='val_loss', factor=0.1,
        patience=0, min_lr=0.0001))

    if save_to:
        callbacks.append(ModelCheckpoint(filepath=save_to, verbose=1))

    model.fit_generator(generator=train_generator,
            samples_per_epoch=train_generator.n,
            nb_epoch=2,
            validation_data=valid_generator,
            nb_val_samples=1000,
            callbacks=callbacks,
            verbose=VERBOSE)

    # Save the weights on completion.
    if save_to:
        model.save_weights(save_to)


def load_model(input_tensor=None, include_top=True):
    if input_tensor is None:
        input_tensor = Input(shape=(IMAGE_SIZE, IMAGE_SIZE, 3))

    # Don't include VGG fc layers.
    base_model = VGG16(include_top=False, input_tensor=input_tensor)

    # Freeze all layers in pretrained network.
    for layer in base_model.layers:
        layer.trainable = False

    x = base_model.output
    x = Flatten(name='flatten')(x)
    x = Dense(4096, activation='relu', name='fc1')(x)
    x = Dropout(0.5)(x)
    x = Dense(2048, activation='relu', name='fc2')(x)
    x = Dropout(0.5)(x)

    if include_top:
        x = Dense(NUM_CLASSES, activation='softmax', name='predictions')(x)

    return Model(inputs=input_tensor, outputs=x)


def test(model, nb_batch=32, nb_worker=2):
    # Optimizer is unused.
    model.compile(loss='categorical_crossentropy', optimizer='sgd',
                  metrics=['accuracy'])

    # Center and normalize each sample.
    normalize = samplewise_normalize(IMAGE_MEAN, IMAGE_STD)

    # Get streaming data.
    test_generator = get_data(VALID_DIR, batch=nb_batch, shuffle=True,
            preprocess=normalize)

    matrix = np.zeros((NUM_CLASSES, NUM_CLASSES))

    # Flag that batch_index at 0 has been seen.
    start = False

    while not start or test_generator.batch_index != 0:
        start = True

        # Grab the next batch.
        x, y_true = test_generator.next()

        # Convert probabilities to predictions.
        y_true = np.argmax(y_true, axis=1)
        y_pred = np.argmax(model.predict_on_batch(x), axis=1)

        matrix += confusion_matrix(y_true, y_pred, labels=range(NUM_CLASSES))

    return matrix


if __name__ == '__main__':
    mvcnn = load_model()
    load_weights(mvcnn, MODEL_WEIGHTS)

    print("Log file: %s" % LOG_FILE)
    train(mvcnn, save_to=MODEL_WEIGHTS)
