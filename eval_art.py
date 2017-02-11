"""
evaluate the changedetection method on artifical dataset
"""
import pandas as pd
import os
from localutils import changedetect as dc, benchmark as bch
import logging
import ConfigParser
import traceback
import multiprocessing

METHOD = ['cpt_normal', 'cpt_poisson', 'cpt_np']
PENALTY = ["SIC", "BIC", "MBIC", "AIC", "Hannan-Quinn"]
WINDOW = 2  # perform evaluation with window size equaling 2


def worker(f):
    f_base = os.path.basename(f)
    r = []
    logging.info("handling %s" % f)
    trace = pd.read_csv(f, sep=';')
    fact = trace['cp']
    fact = [i for i, v in enumerate(fact) if v == 1]  # fact in format of data index
    logging.debug("%s : change counts %d" % (f_base, len(fact)))
    for m, p in [(x, y) for x in METHOD for y in PENALTY]:
        logging.debug("%s: evaluating %s with %s" % (f_base, m, p))
        method_caller = getattr(dc, m)
        detect = method_caller(trace['rtt'], penalty=p)
        b = bch.evaluation_window_weighted(trace['rtt'], fact, detect, WINDOW)
        r.append((os.path.basename(f), len(trace), len(fact),
                  b['tp'], b['fp'], b['fn'],
                  b['precision'], b['recall'], b['score'], b['dis'], m+'&'+p))
        logging.debug('%r' % b)
    return r


def worker_wrapper(args):
    try:
        return worker(args)
    except Exception:
        logging.critical("Exception in worker.")
        traceback.print_exc()
        raise


def main():
    # logging setting
    logging.basicConfig(filename='eval_art.log', level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S %z')

    # load data collection configuration from config file in the same folder
    config = ConfigParser.ConfigParser()
    if not config.read('./config'):
        logging.critical("Config file ./config is missing.")
        return

    # load the configured directory where collected data shall be saved
    try:
        data_dir = config.get("dir", "data")
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
        logging.critical("config for data storage is not right.")
        return

    # check if the directory is there
    if not os.path.exists(data_dir):
        logging.critical("data folder %s does not exisit." % data_dir)
        return

    # load where artificial traces are stored
    try:
        art_dir = config.get("dir", "artificial_trace")
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
        logging.critical("config for artificial trace storage is not right.")
        return

    # check if the folder is there
    if not os.path.exists(art_dir):
        logging.critical("folder %s does not exisit." % data_dir)
        return

    files = []
    for f in os.listdir(art_dir):
        if f.endswith('.csv') and not f.startswith('~'):
            files.append(os.path.join(art_dir,f))

    pool = multiprocessing.Pool(processes=2)
    res = pool.map(worker_wrapper, files)

    #res = [worker(i) for i in files]

    with open(os.path.join(data_dir, 'eval_art.csv'), 'w') as fp:
        fp.write(';'.join(
            ['file', 'len', 'changes', 'tp', 'fp', 'fn', 'precision', 'recall', 'score', 'dis', 'method']) + '\n')
        for ck in res:
            for line in ck:
                fp.write(";".join([str(i) for i in line]) + '\n')


if __name__ == '__main__':
    main()
