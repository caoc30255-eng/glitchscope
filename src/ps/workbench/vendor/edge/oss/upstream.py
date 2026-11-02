"""PC-only upstream training/query adapter; never import on the board."""
import numpy as np
from sklearn.base import BaseEstimator,ClassifierMixin
from sklearn.ensemble import RandomForestRegressor
from skactiveml.classifier import SklearnClassifier
from skactiveml.pool import UncertaintySampling

CONFIG=dict(n_estimators=31,max_depth=5,min_samples_leaf=3,max_features=1.0,random_state=20261026,n_jobs=1)
class ProbabilityForest(ClassifierMixin,BaseEstimator):
    def __init__(self,seed=20261026):self.seed=seed
    def fit(self,X,y,sample_weight=None):
        self.regressor_=RandomForestRegressor(**dict(CONFIG,random_state=self.seed))
        self.regressor_.fit(X,y,sample_weight=sample_weight);self.classes_=np.array([0,1]);self.n_features_in_=len(X[0]);return self
    def predict_proba(self,X):
        p=np.clip(self.regressor_.predict(X),0,1);return np.column_stack([1-p,p])
    def predict(self,X):return (self.predict_proba(X)[:,1]>.5).astype(int)
def fit(X,y,seed=20261026):
    clf=SklearnClassifier(ProbabilityForest(seed),classes=[0,1],missing_label=np.nan,random_state=seed)
    clf.fit(np.asarray(X,dtype=float),np.asarray(y,dtype=float));return clf
def utilities(clf,X,y,candidates):
    query=UncertaintySampling(method='entropy',random_state=20261026)
    indices,u=query.query(np.asarray(X,dtype=float),np.asarray(y,dtype=float),clf,
        fit_clf=False,candidates=np.asarray(candidates,dtype=float),batch_size=1,return_utilities=True)
    return indices.tolist(),u[0].tolist()
