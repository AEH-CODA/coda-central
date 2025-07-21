
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score

def run(*args, **kwargs):
    # Load the local dataset provided to the node
    df = kwargs.get("data")

    if df is None:
        return {"error": "No data provided!"}

    # Assuming the last column is the target
    X = df.iloc[:, :-1]
    y = df.iloc[:, -1]

    # Standardize features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Train-test split
    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, y, test_size=0.2, random_state=42
    )

    # Train Logistic Regression
    model = LogisticRegression()
    model.fit(X_train, y_train)

    # Predict and calculate accuracy
    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)

    return {"accuracy": accuracy}
