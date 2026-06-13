class EnsembleClassifierWrapper:
    """Wrapper class to provide seamless compatibility with main.py, train_model.py, and SHAP."""
    def __init__(self, voting_clf, label_encoder, feature_means=None, feature_stds=None):
        self.voting_clf = voting_clf
        self.label_encoder = label_encoder
        self.classes_ = label_encoder.classes_
        self.feature_means = feature_means or {}
        self.feature_stds = feature_stds or {}
        
    def predict(self, X):
        preds = self.voting_clf.predict(X)
        return self.label_encoder.inverse_transform(preds)
        
    def predict_proba(self, X):
        return self.voting_clf.predict_proba(X)
        
    @property
    def feature_importances_(self):
        rf_model = self.voting_clf.named_estimators_['rf']
        return rf_model.feature_importances_
