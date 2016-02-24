from __future__ import division

import itertools
import json
import matplotlib.pyplot as plt
import numpy as np
import sys

from Bio.Data import CodonTable
from collections import defaultdict
from scipy import misc
from sklearn import cross_validation
from sklearn import feature_selection
from sklearn import preprocessing
from sklearn import svm
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.cross_validation import train_test_split
from sklearn.decomposition import PCA
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.externals import joblib
from sklearn.feature_selection import SelectFromModel, SelectKBest, f_classif, RFE
from sklearn.metrics import average_precision_score
from sklearn.metrics import brier_score_loss
from sklearn.metrics import f1_score
from sklearn.metrics import precision_recall_curve
from sklearn.metrics import precision_score
from sklearn.metrics import recall_score
from sklearn.naive_bayes import GaussianNB
from sklearn.pipeline import FeatureUnion
from sklearn.pipeline import Pipeline
from sklearn.utils import shuffle
from sklearn.linear_model import LassoCV



codon_identifier = dict(("".join(v), k)
                        for k, v in enumerate(itertools.product('ATGC', repeat=3)))


class Classifier:
    """This is a classifier for codon rassignment"""

    def __init__(self, method, classifier_spec={}, scale=False, n_estimators=1000):

        if method == 'rf':
            self.clf = RandomForestClassifier(
                n_estimators=n_estimators, n_jobs=-1, max_leaf_nodes=100, **classifier_spec)
        elif method == 'svc':
            self.clf = svm.SVC(probability=True, **classifier_spec)
        elif method == 'etc':
            self.clf = ExtraTreesClassifier(
                n_estimators=n_estimators, **classifier_spec)
        elif method == 'gnb':
            self.clf = GaussianNB()            
        else:
            raise NotImplementedError("The method you chose (%s) is not implemented"%method)

        self.method = method
        self.trained = False
        self.scale = scale

    def load_from_file(self, loadfile):
        """ Load model from a file"""
        try:
            self.clf = joblib.load(loadfile)
            self.trained = True
        except IOError:
            print('Problem with file %s, can not open it' % loadfile)
        except Exception as e:
            print(e)

    def save_model(self, outfile):
        """Save model to a file"""
        joblib.dump(self.clf, outfile)

    def train(self, X=None, Y=None):
        """Train the model"""
        if self.scale:
            X = preprocessing.scale(X)
        self.clf.fit(X, Y)
        self.trained = True

    def get_score(self, X, Y):
        """ Return score for classification on X"""
        if self.scale:
            X = preprocessing.scale(X)
        return self.clf.score(X, Y)

    def predict(self, X):
        """ Predict values for X"""
        if not self.trained:
            raise ValueError("Classifier is not trained")
        if self.scale:
            X = preprocessing.scale(X)
        return self.clf.predict(X)

    def predict_proba(self,X):
        """ Return probability for each class prediction"""
        return self.clf.predict_proba(X)

    def feature_importance(self, outfile="importance.png", features_list=[]):
        """Show each feature importance"""
        if (self.method in ['rf', 'etc']):
            importances = self.clf.feature_importances_

            if len(features_list) > 0 and len(features_list) != len(importances):
                raise ValueError("Number of features does not fit!")

            indices = np.argsort(importances)[::-1]
            n_feats = len(features_list)
            std = np.std(
                [tree.feature_importances_ for tree in self.clf.estimators_], axis=0)
            plt.figure()
            plt.title("Feature importances")
            plt.bar(range(n_feats), importances[
                    indices], width=0.5, color="b", yerr=std[indices], align="center")
            if len(features_list) > 0:
                features_list = np.asarray(features_list)[indices]
                plt.xticks(range(n_feats), features_list, rotation='vertical')
            plt.xlim([-1, n_feats])
            plt.margins(0.2)

            plt.subplots_adjust(bottom=0.15)
            plt.savefig(outfile, bbox_inches='tight')
        else:
            raise NotImplementedError("Not supported for classifier other than Ensembl Tree")

    def cross_validation(self, X, Y, X_test=None, Y_test=None, tsize=0.3):
        """Cross validation on X and Y, using a sub sample"""
        if X_test is None or Y_test is None:
            X_train, X_test, Y_train, Y_test = train_test_split(
                X, Y, test_size=tsize)
        else:
            X_train = X
            Y_train = Y
        self.train(X_train, Y_train)
        Y_predicted = self.predict(X_test)
        return Y_predicted, self.get_score(X_test, Y_test)

    def plot_precision_recall(self, X_test, y_test, infos="", outfile="precision_recall.png"):
        """ plot precicion-recall curve"""
        if self.trained:
            y_score = self.clf.decision_function(X_test)
            precision, recall, _ = precision_recall_curve(y_test, y_score)
            average_precision = average_precision_score(y_test, y_score, average="micro")
            # Plot Precision-Recall curve for each class
            plt.clf()
            plt.plot(recall, precision,
            label='micro-average Precision-recall curve (area = {0:0.2f})'
                  ''.format(average_precision["micro"]))
            plt.xlim([0.0, 1.0])
            plt.ylim([0.0, 1.05])
            plt.xlabel('Recall')
            plt.ylabel('Precision')
            plt.title('Precision-Recall curve for %s (%s)'%(self.method, infos))
            plt.legend(loc="lower right")
            plt.savefig(outfile)


    def get_stat(self, X_test, y_test):
        """Print list of score for the current classifier"""
        y_pred = self.predict(X_test)
        if hasattr(self.clf, "predict_proba"):
            prob_pos = self.clf.predict_proba(X_test)[:, 1]
        else:  # use decision function
            prob_pos = self.clf.decision_function(X_test)
            prob_pos = (prob_pos - prob_pos.min()) / (prob_pos.max() - prob_pos.min())

        clf_score = brier_score_loss(y_test, prob_pos)
        print("%s:" % self.method)
        print("\tBrier: %1.3f" % (clf_score))
        print("\tPrecision: %1.3f" % precision_score(y_test, y_pred))
        print("\tRecall: %1.3f" % recall_score(y_test, y_pred))
        print("\tF1: %1.3f\n" % f1_score(y_test, y_pred))


    def plot_calibration_curve(self, X_test, y_test, caltype="isotonic", outfile=None):
        name = self.method
        if self.trained:
            calib = CalibratedClassifierCV(self.clf, cv=2, method=caltype)
            lr = LogisticRegression(C=1., solver='lbfgs')
            fig = plt.figure(fig_index, figsize=(10, 10))
            ax1 = plt.subplot2grid((3, 1), (0, 0), rowspan=2)
            ax2 = plt.subplot2grid((3, 1), (2, 0))

            ax1.plot([0, 1], [0, 1], "k:", label="Perfectly calibrated")
            for clf, name in [(lr, 'Logistic'),(self.clf, name),
                              (calib, name + ' + '+caltype)]:
                y_pred = clf.predict(X_test)
                if hasattr(clf, "predict_proba"):
                    prob_pos = clf.predict_proba(X_test)[:, 1]
                else:  # use decision function
                    prob_pos = clf.decision_function(X_test)
                    prob_pos = \
                        (prob_pos - prob_pos.min()) / (prob_pos.max() - prob_pos.min())

                clf_score = brier_score_loss(y_test, prob_pos)
                fraction_of_positives, mean_predicted_value = \
                    calibration_curve(y_test, prob_pos, n_bins=10)

                ax1.plot(mean_predicted_value, fraction_of_positives, "s-",
                         label="%s (%1.3f)" % (name, clf_score))

                ax2.hist(prob_pos, range=(0, 1), bins=10, label=name,
                         histtype="step", lw=2)

            ax1.set_ylabel("Fraction of positives")
            ax1.set_ylim([-0.05, 1.05])
            ax1.legend(loc="lower right")
            ax1.set_title('Calibration plots  (reliability curve)')

            ax2.set_xlabel("Mean predicted value")
            ax2.set_ylabel("Count")
            ax2.legend(loc="upper center", ncol=2)
            plt.tight_layout()
            if outfile == None:
                outfile =  "calibration_curve_"+name+".png"
            plt.savefig(outfile)


def read_from_json(data, labels, use_global=True, use_pvalue=True):
    """Parse X array from data"""
    if isinstance(data, basestring):
        with open(data) as jfile:
            data = json.load(jfile)

    if isinstance(labels, basestring):
        with open(labels) as jfile2:
            labels = json.load(jfile2)
    # matrice format
    # global
    min_value = np.finfo(np.float).min
    dtype = 'global'
    if not use_global:
        dtype = 'filtered'

    fisher_type = 'pass'
    if use_pvalue:
        fisher_type = 'pval'
    X = []
    X_label = []
    Y = []
    # each entry format :
    # [fitch, suspected, gene_frac, rea_frac, used_frac, subs_count, codon_lik_for_rea_aa]
    for aa2, val in data['aa'].items():
        for aa1, glist in val.items():
            for genome, gdata in glist.items():
                type_check = gdata[dtype]
                codon_total = gdata['codons'][dtype]
                fitch = gdata['fitch']
                suspected = gdata['suspected'] < 0.05
                rea_codon = type_check['rea_codon']
                mixte_codon = type_check['mixte_codon']
                used_codon = type_check['used_codon']
                gene_in_genome = data['genes'][genome]
                was_lost = gdata['lost'][fisher_type]
                #mixte_codon = type_check['mixte_codon']
                subs_count = type_check['count']
                for codon in codon_total.keys():
                    gene_count = 0
                    total_gene_count = 0
                    try:
                        gene_count = len(type_check[
                            'rea_distribution'].get(codon, []))
                        total_gene_count = len(type_check[
                            'total_rea_distribution'].get(codon, []))
                    except:
                        gene_count = type_check[
                            'rea_distribution'].get(codon, 0)
                        total_gene_count = type_check[
                            'total_rea_distribution'].get(codon,0)
    
                    codon_count = codon_total[codon]
                    try:
                        codon_lik = gdata['score'][
                            dtype].get(codon, min_value)
                        if codon_lik == np.inf:
                            codon_lik = min_value
                    except:
                        codon_lik = min_value

                    # si il y a mutation, frequence d'utilisation du codon
                    rea_frac = rea_codon.get(
                        codon, 0) * (1.0 / codon_count) if codon_count > 0 else 0
                    # frequence d'utilisation du codon dans les positions
                    # ou l'acide amine est predo
                    used_frac = used_codon.get(
                        codon, 0) * (1.0 / codon_count) if codon_count > 0 else 0
                    mixte_frac = mixte_codon.get(
                        codon, 0) * (1.0 / codon_count) if codon_count > 0 else 0
                    gene_frac = gene_count * (1.0 / total_gene_count) if total_gene_count > 0 else 0
                    codon_id = codon_identifier[codon]
                    genome_len = data["genome"][dtype][genome]
                    # only add codon tha are reassigned else it does not
                    # make sense, right?
                    
                    entry = [fitch, suspected, was_lost, gene_frac, rea_frac, used_frac,
                                 codon_count, subs_count, genome_len, codon_lik, mixte_frac, codon_id]
                    X.append(entry)
                    X_label.append([genome, codon, aa2, aa1])
                    codon_mapper = None
                    try:
                        codon_mapper = labels[genome][codon]
                    except:
                        pass
                    if codon_mapper is None:
                        Y.append(-1)
                    else:
                        Y.append(codon_mapper.get(aa1, -1))
                        # keep only what is well defined
                        # anything else will have a class of -1 to mean unsure
    assert (len(X) == len(
        Y)), "We should not have different length for data and for label"
    return np.array(X), X_label, np.array(Y)


def get_labels_from_csvfile(csvfile, genetic_code):
    """ Get labels from a csvfile. Won't be used anymore"""
    def makehash():
        return defaultdict(makehash)
    codontable = CodonTable.unambiguous_dna_by_id[genetic_code]
    labels = makehash()
    with open(csvfile) as labfile:
        for line in labfile:
            line = line.strip()
            if line and not line.startswith('#'):
                genome, codon, reassignment = line.split()
                codon = codon.upper().replace('U', 'T')
                if len(codon) == 3 and codontable.forward_table[codon] != reassignment.upper():
                    labels[genome][codon] = reassignment
    return labels


def get_2D_distinct(Xdata, Xlabel, y, etiquette, outfile="2Dcompare.png", features=[]):
    """ project feature in 2D to check data separation"""
    color = np.empty(y.shape[0], dtype="S7")
    color[y == 0] = '#dddddd'
    color[np.logical_and((y == 1), (Xlabel[:, 3] == 'G'))] = '#00ff00'
    color[np.logical_and((y == 1), (Xlabel[:, 3] == 'N'))] = '#000080'
    color[np.logical_and((y == 1), (Xlabel[:, 3] == 'M'))] = '#FF55A3'
    color[np.logical_and((y == 1), (Xlabel[:, 3] == 'S'))] = '#FFD800'
    color[np.logical_and((y == 1), (Xlabel[:, 3] == 'K'))] = '#00ffd8'
    indices = np.argsort(y)
    Xdata = Xdata[indices, :]
    y = y[indices]

    ncomp = len(features)
    if ncomp == 0 or ncomp > len(etiquette):
        ncomp = len(etiquette)
        features = range(len(etiquette))
    else:
        Xdata = Xdata[:, features]

    total_size = int(misc.comb(ncomp, 2))

    i = int(np.floor(np.sqrt(total_size)))
    j = int(np.ceil(total_size / i))

    plt.close('all')
    f, axarr = plt.subplots(i, j)

    for xax in xrange(ncomp):
        for yax in xrange(xax + 1, ncomp):
            total_size -= 1
            i, j = np.unravel_index(total_size, axarr.shape)
            axarr[i, j].scatter(Xdata[:, xax], Xdata[:, yax], c=color)
            axarr[i, j].set_xlabel(etiquette[features[xax]], fontsize=6)
            axarr[i, j].set_ylabel(etiquette[features[yax]], fontsize=6)
    for axe in np.ravel(axarr):
        axe.tick_params(axis='both', which='both', bottom='off', labelbottom='off',
                        labeltop='off', top='off', right='off', left='off', labelleft='off')
    plt.tight_layout()
    plt.savefig(outfile)


def get_features(Xdata, y=None, ncomp=2, kbest=0):
    """Feature selection using PCA or Kbest variance selection"""
    if ncomp>0 and kbest>0:
        pca = PCA(n_components=ncomp)
        selection = SelectKBest(f_classif, k=(int(kbest) if int(kbest)<Xdata.shape[1] else 'all'))
        combined_features = FeatureUnion([("pca", pca), ("univ_select", selection)])
        X_features = combined_features.fit_transform(Xdata, y)
    
    elif ncomp > 0:
        pca = PCA(n_components=ncomp)
        X_features = pca.fit_transform(Xdata, y)
    
    elif kbest > 0:
        selection = SelectKBest(k=int(kbest) if int(kbest)<Xdata.shape[1] else 'all')
        X_features = selection.fit_transform(Xdata, y)
       
    return X_features


def draw_pca_data(X_features, Xlabel, y, outfile="PCA.png"):
    """ Draw pca data and save in a file"""
    color = np.empty(y.shape[0], dtype="S7")
    color[y == 0] = '#dddddd'
    color[np.logical_and((y == 1), (Xlabel[:, 3] == 'G'))] = '#00ff00'
    color[np.logical_and((y == 1), (Xlabel[:, 3] == 'N'))] = '#000080'
    color[np.logical_and((y == 1), (Xlabel[:, 3] == 'M'))] = '#FF55A3'
    color[np.logical_and((y == 1), (Xlabel[:, 3] == 'S'))] = '#FFD800'
    color[np.logical_and((y == 1), (Xlabel[:, 3] == 'K'))] = '#00ffd8'

    ncomp = X_features.shape[1]
    total_size = int(misc.comb(ncomp, 2))
    i = int(np.floor(np.sqrt(total_size)))
    j = int(np.ceil(total_size / i))

    plt.close('all')
    f, axarr = plt.subplots(i, j)
    if total_size > 1:
        for xax in xrange(ncomp):
            for yax in xrange(xax + 1, ncomp):
                total_size -= 1
                i, j = np.unravel_index(total_size, axarr.shape)
                axarr[i, j].scatter(X_features[:, xax],
                                    X_features[:, yax], c=color)
                axarr[i, j].set_title('%d vs %d' % (xax, yax), fontsize=6)

        for ax in axarr.flatten():
            ax.tick_params(axis='both', which='both', bottom='off', labelbottom='off',
                        labeltop='off', top='off', right='off', left='off', labelleft='off')
    else:
        axarr.scatter(X_features[:, 0],
                                    X_features[:, 1], c=color)
        axarr.set_title('%d vs %d' % (1, 2))
        axarr.tick_params(axis='both', which='both', bottom='off', labelbottom='off',
                        labeltop='off', top='off', right='off', left='off', labelleft='off')
    plt.tight_layout()
    plt.savefig(outfile)


def print_data(X, X_label, Y, etiquette=None):
    """ Print data"""
    if etiquette is None:
        etiquette = ["fitch", "suspected", "Fisher pval", "Gene frac", "N. rea",
                     "N. used", "Cod. count", "Sub. count", "G. len", "codon_lik", "N. mixte", "id"]
    etiquette = list(etiquette)

    print("\n" + "\t".join(["genome", "codon",
                            "ori_aa", "rea_aa"] + etiquette))
    for i in xrange(len(X_label)):
        if Y[i] == 1:
            print("\t".join(list(X_label[i]) + [str(x) for x in X[i]]))


def getDataFromFeatures(Xdata, etiquette, feats=[]):
    """Extract Data based on list of features"""
    if len(feats) == 0:
        return Xdata, etiquette
    else:
        return Xdata[:, feats], np.asarray(etiquette)[feats]


def get_sensibility_and_precision(pred_y, true_y, X_labels=None, X=None, log=True):
    """ Get sensibility and precision after classification"""
    nel = len(true_y)
    assert nel == len(pred_y), 'Vector should be the same size\n'
    true_pos, true_neg, false_pos, false_neg = 0.0, 0.0, 0.0, 0.0
    false_neg_list, false_pos_list = [], []
    for i in xrange(len(pred_y)):
        if pred_y[i] == 0 and true_y[i] == 1:
            false_neg += 1
            false_neg_list.append(i)
        elif pred_y[i] == 1 and true_y[i] == 0:
            false_pos += 1
            false_pos_list.append(i)
        elif pred_y[i] == 1 and true_y[i] == 1:
            true_pos += 1
        elif pred_y[i] == 0 and true_y[i] == 0:
            true_neg += 1

    if log:
        print("Test size is: %d\nTrue Positive is: %d\nTrue negative is: %d\nFalse positive is: %d\nFalse negative is:%d" % (nel, true_pos, true_neg, false_pos, false_neg))
        print('-------------------------------------------')
        print("Sensibility is %f" % (true_pos / (true_pos + false_neg) if (true_pos + false_neg) > 0 else 1))
        print("Specificity is %f" % (true_neg / (true_neg + false_pos) if (true_neg + false_pos) > 0 else 1))
        print("Accuracy is %f" % ((true_neg + true_pos) / nel))
        print("Precision is %f\n\n" % (true_pos / (true_pos + false_pos) if (true_pos + false_pos) > 0 else 1))
        if X_labels is not None and X is not None:
            if len(false_neg_list) > 0:
                print("List of false negatives")
                for i in false_neg_list:
                    print("\t".join(X_labels[i]))
                    print("\t".join([str(x) for x in X[i]]))

            if len(false_pos_list) > 0:
                print("\nList of False positives")
                for i in false_pos_list:
                    print("\t".join(X_labels[i]))
                    print("\t".join([str(x) for x in X[i]]))


def split_zeros_pos(L, X, Y, split_size=300):
    zero_pos = np.where(Y == 0)[0]
    np.random.shuffle(zero_pos)
    tlen = len(zero_pos)
    nsplit = np.floor(tlen / split_size)
    if tlen <= split_size:
        yield (X[zero_pos], L[zero_pos], Y[zero_pos])
    else:
        delim = tlen - tlen % split_size
        last_chunck = zero_pos[delim:]
        chuncks = np.split(zero_pos[:delim], nsplit)
        chuncks.append(last_chunck)
        for ch in chuncks:
            yield (X[ch], L[ch], Y[ch])

def get_test_from_dataset(L, X, Y, AA, tsize=0.3, rstate=0):
    test_position = []
    for i in xrange(len(Y)):
        if L[i][-1] == AA:
            test_position.append(i)

    if tsize:
        t_len = int(tsize * len(Y))
        zero_pos = np.where(Y == 0)[0]

        test_len = len(test_position)
        random_zero_pos = np.random.choice(zero_pos, t_len, replace=False)
        test_position.extend(random_zero_pos)

    test_position = np.random.permutation(test_position)
    mask = np.ones(Y.shape, dtype=bool)
    mask[test_position] = False
    return shuffle(X[mask], Y[mask], np.array(range(len(mask)))[mask], random_state=rstate), shuffle(X[~mask], Y[~mask], np.array(range(len(mask)))[~mask], random_state=rstate)


def feature_selection_test(X, y, features, nfeat=8):
    # univariate selection
    

    features = np.asarray(features)
    selected_feats = [0,2,3,4,5,7,8,9]
    print("------------------------------------------\nManually selected features : ")
    print(", ".join(features[selected_feats]))


    y = np.asarray(y)
    uvariate_selection = SelectKBest(f_classif, k=nfeat)
    uvariate_selection.fit(X, y)
    support_array = uvariate_selection.get_support()
    print("------------------------------------------\nSelected features by univariate : ")
    print(", ".join(features[support_array]))

    # Select with feature_importances
    clf = ExtraTreesClassifier()
    clf = clf.fit(X, y)
    clf.feature_importances_  
    model = SelectFromModel(clf, prefit=True)
    support = model.get_support()
    print("------------------------------------------\nSelected features by feature_importances_ : ")
    print(", ".join(features[support]))

    # Use linear SVC with penality
    lsvc = svm.LinearSVC(C=0.2, penalty="l1", dual=False).fit(X, y)
    model = SelectFromModel(lsvc, prefit=True)
    support = model.get_support()
    print("------------------------------------------\nSelected features by Linear SVC and penalty : ")
    print(", ".join(features[support]))

    # Use Lasso

    clf = LassoCV()
    model = SelectFromModel(clf, threshold=0.01)
    model.fit(X, y)
    support = model.get_support()
    print("------------------------------------------\nSelected features by Lasso : ")
    print(", ".join(features[support]))

    # Recursive feature selection 
    svc = svm.SVC(kernel="linear", C=1)
    rfe = RFE(estimator=svc, n_features_to_select=nfeat, step=1)

    clf = RandomForestClassifier(n_estimators=1000, n_jobs=-1, max_leaf_nodes=100)
    rfe2 = RFE(estimator=clf, n_features_to_select=nfeat, step=1)

    rfe.fit(X, y)
    rfe2.fit(X, y)
    ranking1 = rfe.ranking_
    ranking2 = rfe2.ranking_
    
    n_feats = len(ranking1)
    f, axarr = plt.subplots(2, 1)
    axarr[0].bar(range(n_feats), ranking1, width=0.5, color="b", align="center")
    axarr[1].bar(range(n_feats), ranking2, width=0.5, color="b", align="center")
    axarr[0].set_title("Features using linear svc")
    axarr[1].set_title("Features using RF")
    for ax in axarr:
        ax.tick_params(axis='both', which='both', labeltop='off', top='off', left='off')
    plt.xlim([-1, n_feats])
    # Set the ticks and ticklabels for all axes
    plt.setp(axarr, xticks=range(n_feats), xticklabels=features)
    plt.tight_layout()
    plt.show()
