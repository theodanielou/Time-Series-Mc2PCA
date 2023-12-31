import numpy as np
import pandas as pd
from tqdm import tqdm
import pickle
from scipy.spatial.distance import cosine
from dtw import dtw

class Mc2PCA() :
    def __init__(self, 
                    K : int,
                    p : int,
                    epsilon : float = 1e-7,
                    max_iter : int = 100, 
                    distance_metric : str = 'euclidean') :
        """
        Perform the Mc2PCA algorithm on the given DataFrame or NumPy array.
        Implementation following the algorithm described in the paper:
        Li, H. (2019). Multivariate time series clustering based on common principal component analysis. Neurocomputing, 349.

        Args: 
            K (int): The number of clusters to form using k-means.
            p (int): The number of principal components to retain in CPCA.
            epsilon (float): The threshold for convergence. 
            max_iter (int, optional): The maximum number of iterations for the clustering algorithm. Defaults to 100.
            distance_metric (str, optional): The distance metric to use for the clustering algorithm. The values can be: 'euclidean', 'cosine', 'dtw', 'l1'. Defaults to 'euclidean'.
            S (list of ndarray): A list of K arrays, each array containing the common space of the kth cluster.
            idx (list of list of int): A list of K lists, each containing the indices of the samples in the kth cluster.
            E (list of float): A list containing the errors at each iteration.
            info_by_cluster (list of float): A list containing the information percentage retained by each cluster.
        """
        self.K = K
        self.p = p
        self.epsilon = epsilon
        self.max_iter = max_iter
        self.distance_metric = distance_metric
        self.S = None
        self.idx = None
        self.E = None
        self.info_by_cluster = None


    def fit(self, X : np.ndarray or pd.DataFrame):
        """
        Fit the model to the given data.

        Args:
            X (DataFrame or ndarray): The input MTS that can be stored as a DataFrame containing the data with samples as 
                                        rows and variables as columns, and each cell containing a pandas Series 
                                        object or a numpy ndarray, OR a 2D NumPy array with the same shape and containing
                                        a 1D NumPy array in each cell.
        """

        # if X is a dataframe, convert into npy array
        if isinstance(X, pd.DataFrame):
            X = convert_to_numpy(X)

        # Center the data
        X = center_data(X)
        # Compute the covariance matrices of each time series
        cov_matrices = compute_covariance_matrices(X)
    
        # Initialize the indices
        idx = np.array_split(np.arange(X.shape[0]), self.K)
        # Initialize the associated common spaces
        S, _ = compute_common_spaces(cov_matrices,idx,self.p)

        # Store the errors
        E = [np.inf]

        for t in tqdm(range(1, self.max_iter + 1), leave=False):

            # Assign the clusters based on k-means
            I,v = assign_clusters(X,S,self.K, distance_metric= self.distance_metric)
            E.append(np.sum(v)/len(v)) # normalize the error

            # Check convergence
            if np.abs(E[t-1] - E[t]) < self.epsilon:
                break
            
            # Assign new clusters
            idx = [np.where(I == k)[0] for k in range(self.K)]

            # Compute the new common spaces after the assignment
            S, info_by_cluster = compute_common_spaces(cov_matrices,idx,self.p)

        # Store the results in the class attributes
        self.info_by_cluster = info_by_cluster
        self.idx = idx
        self.E = E
        self.S = S
        return idx, E, info_by_cluster

    def inference(self, X_test : np.ndarray or pd.DataFrame):
        """  
        Perform inference on the given test set using the learned model.

        Args:
            X_test (DataFrame or ndarray): The input MTS that can be stored as a DataFrame containing the data with samples as 
                        rows and variables as columns, and each cell containing a pandas Series 
                        object or a numpy ndarray, OR a 2D NumPy array with the same shape and containing
                        a 1D NumPy array in each cell.
            
        """

        # if X is a dataframe, convert into npy array
        if isinstance(X_test, pd.DataFrame):
            X_test = convert_to_numpy(X_test)  

        # Center the data
        X_test = center_data(X_test)

        # Assign the clusters based on k-means using the learned common spaces
        I, _ = assign_clusters(X_test, self.S, self.K, distance_metric = self.distance_metric)
        
        # Assign new clusters
        idx = [np.where(I == k)[0] for k in range(self.K)]

        return idx
    
    def save_model(self, path: str):
        """
        Save the model using pickle.

        Args:
            path (str): The path to the file where the model should be saved.
        """
        with open(path, 'wb') as file:
            pickle.dump(self, file)
        

    def load_model(cls, path: str):
        """
        Load a model using pickle.

        Args:
            path (str): The path to the file from which the model should be loaded.

        Returns:
            Mc2PCA: The loaded model.
        """
        with open(path + '.pkl', 'rb') as file:
            return pickle.load(file)


def convert_to_numpy(df):
    """
    Convert a DataFrame where each cell contains a pandas Series into a 1D NumPy array.

    Args:
        df (DataFrame): The input DataFrame containing the data with samples as rows and variables as columns, 
                        and each cell containing a pandas Series object, or a numpy ndarray.
    
    Returns:
        ndarray: The 2D NumPy array containing the data with samples as rows and variables as columns, 
                 and each cell containing a 1D NumPy array.
    """

    # First convert the pandas series to ndarray if necessary
    if isinstance(df.iloc[0,0], pd.Series):
        for col_name in df.columns:
            df[col_name] = df[col_name].apply(lambda series: series.to_numpy() if series is not None else np.nan)

    df_npy = df.to_numpy()

    return df_npy
 

def center_data(X) :
    """
    Center the data by subtracting the mean of each time series from each cell.

    Args:
        X (ndarray): The input 2D NumPy array containing the multivariate time series data with samples as rows and variables as columns, and each cell containing a 1D numpy ndarray.
    
    Returns:
        ndarray: The centered 2D NumPy array.
    """
    n, m = X.shape  # Number of samples and features
    centered_X = np.empty_like(X)

    for i in range(n):
        for j in range(m):
            time_series = X[i, j]
            mean = np.mean(time_series)
            centered_X[i, j] = time_series - mean

    return centered_X
         

def compute_covariance_matrices(centered_X):
    """
    Compute the covariance matrix of each time series in the given 2D Numpy array.

    Args:
        centered_X (ndarray): The input 2D NumPy array containing the centered multivariate time series data, 
                              where each cell contains a 1D NumPy array representing a time series.
    
    Returns:
        list: A list containing the covariance matrix of each time series in the given array.
    """
    n,m = centered_X.shape

    # Store the covariance matrix of each time series
    cov_matrices = []

    for i in range(n):
        # Extract and stack each time series in the row into a 2D array
        row_data = np.column_stack([centered_X[i, j] for j in range(m) if centered_X[i, j] is not None])

        # Compute the covariance matrix of the time seriif row_data.size > 0:
        cov_matrix = np.cov(row_data.T, bias=True)  
       
        cov_matrices.append(cov_matrix)

    return cov_matrices



def CPCA(Sigma, p):
    """
    Perform Common Principal Component Analysis on a set of covariance matrices corresponding to
    a cluster of a multivariate time series, and return the common space of the cluster.

    Args:
        Sigma (list of ndarray): The list of covariance matrices.
        p (int): The number of principal components to retain.

    Returns:
        ndarray: The common space of the cluster.
    """
    mean_cov = np.mean(Sigma, axis=0) # mean covariance matrix of the cluster
    _, val_propre, vt = np.linalg.svd(mean_cov) # SVD of the mean covariance matrix
    val_propre = val_propre**2 # eigenvalues of the mean covariance matrix
    prct_info =  np.sum(val_propre[:p]/np.sum(val_propre))
    return vt[:p,:].T, prct_info # return the first p principal components and the information retained


def compute_common_spaces(cov_matrices,cluster_indices,p):
    """
    Compute the common principal components of each cluster using CPCA.

    This function iterates over the provided cluster indices and applies CPCA to the 
    covariance matrices corresponding to each cluster. This is used to find a common 
    subspace for each cluster that captures the most variance.

    Args:
        cov_matrices (list of ndarray): A list of covariance matrices for all samples in the dataset.
        cluster_indices (list of list of int): A list of K lists, each containing the indices of the samples in the kth cluster.
        p (int): The number of principal components to retain in CPCA.

    Returns:
        list of ndarray: A list of K arrays, each array containing the common space of the kth cluster.
    """
    S = []
    info_by_cluster = []
    for indices in cluster_indices:
        if len(indices) > 0: # ensure that the cluster is not empty
            vec_propres, prct_info = CPCA([cov_matrices[i] for i in indices], p)
            S.append(vec_propres)
            info_by_cluster.append(prct_info)
        else:
            S.append(None)
    return S, info_by_cluster


def assign_clusters(X,S,K, distance_metric='euclidean'):
    """
    Assign each multivariate time series to a cluster based on the reconstruction error.

    Compute the reconstruction error for each time series after projecting it onto the common space of each cluster.
    Each time series is then assigned to the cluster for which it has the lowest reconstruction error.
    For empty clusters (very unlikely), assign a high error value.

    Args:
        X (ndarray): The input array containing the centered multivariate time series as (nb_samples,nb_variables) 
                        where each cell contains a 1D NumPy array representing a time series.
        S (list of ndarray): A list of K arrays, each array containing the common space of the kth cluster.
        K (int): The number of clusters.
        distance_metric (str, optional): The distance metric to use for error in the clustering algorithm. The values can be: 'euclidean', 'cosine', 'dtw', 'l1'. Defaults to 'euclidean'.
    
    Returns:
        tuple: A tuple containing two elements:
            - ndarray: An array containing the indices of the clusters to which each time series is assigned.
            - ndarray: An array containing containing the minimum reconstruction error for each time series.
    """
    n = X.shape[0]
    Error = np.zeros((n, K))
    
    for k in range(K):
        if S[k] is not None:
            sst = np.matmul(S[k], S[k].T)
            for i in range(n):
                time_series = np.column_stack(X[i, :])  # Stacking the 1D arrays in the row into a 2D array (length,nb_variables)
                Y = np.matmul(time_series, sst)
                if distance_metric == 'euclidean':
                    err = np.linalg.norm(time_series - Y, axis=1)
                elif distance_metric == 'cosine':
                    err = np.array([cosine(time_series[j], Y[j]) for j in range(time_series.shape[0])])
                elif distance_metric == 'dtw':
                    err = np.array([dtw(time_series[j],Y[j]).distance for j in range(time_series.shape[0])])
                elif distance_metric == 'l1':
                    err = np.linalg.norm(time_series - Y, ord=1, axis=1)
                Error[i, k] = np.mean(err)  # Mean error for the time series
        else:
            Error[:, k] = np.inf

    I = np.argmin(Error, axis=1)
    v = Error[np.arange(n), I]
    return I, v