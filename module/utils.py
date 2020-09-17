#!/usr/bin/env python
# -*- coding: utf-8 -*-
# This module uses Numpy & OpenCV(opencv-python). Please install before use it.

import os.path
import numpy as np
import cv2
import pandas as pd
import scipy
import skimage
import time
import re
import ast

from itertools import product
from scipy.ndimage import convolve
from skimage.measure import label, regionprops_table
from skimage.morphology import reconstruction
from numpy import matlib



def str2array(s):
    # Remove space after [
    s=re.sub('\[ +', '[', s.strip())
    # Replace commas and spaces
    s=re.sub('[,\s]+', ', ', s)
    return np.array(ast.literal_eval(s))



def logging_time(original_fn):
    def wrapper_fn(*args, **kwargs):
        start_time = time.time()
        result = original_fn(*args, **kwargs)
        end_time = time.time()
        print("WorkingTime[{}]: {} sec".format(original_fn.__name__, end_time-start_time))
        return result
    return wrapper_fn


def imread(filename, flags=cv2.IMREAD_COLOR, dtype=np.uint8):
    try:
        n = np.fromfile(filename, dtype)
        imageBGR = cv2.imdecode(n, flags)
        return cv2.cvtColor(imageBGR, cv2.COLOR_BGR2RGB)

    except Exception as e:
        print(e)
        return None
    

def normalizeControlPoints(pts):
    
    """
    This code is a Python implementation of Matlab code
    
    'images.geotrans.internal.normalizeControlPoints'
    
    Reference : 
    
    [1] Matlab Code Download link : https://www.mathworks.com/matlabcentral/mlc-downloads/downloads/submissions/46441/versions/3/previews/MarsRover2014/matlab/calibration/myNormalizeControlPoints.m/index.html
    
    [2] Hartley, R; Zisserman, A. "Multiple View Geometry in Computer Vision." Cambridge University Press, 2003. pg. 180-181.

    """
    
    # Define N, the number of control points
    N = pts.shape[0]

    # Compute [xCentroid,yCentroid]
    cent = np.mean(pts, 0)

    # Shift centroid of the input points to the origin.
    ptsNorm = np.zeros((4, 2))
    ptsNorm[:, 0] = pts[:, 0] - cent[0]
    ptsNorm[:, 1] = pts[:, 1] - cent[1]

    sumOfPointDistancesFromOriginSquared = np.sum(np.power(np.hypot(ptsNorm[:, 0], ptsNorm[:, 1]), 2))

    if sumOfPointDistancesFromOriginSquared > 0:
        scaleFactor = np.sqrt(2 * N) / np.sqrt(sumOfPointDistancesFromOriginSquared)
        
    #     else:
    # % If all input control points are at the same location, the denominator
    # % of the scale factor goes to 0. Don't rescale in this case.
    #         if isa(pts,'single'):
    #             scaleFactor = single(1);
    #         else:
    #             scaleFactor = 1.0;
    # % Scale control points by a common scalar scale factor
    
    ptsNorm = np.multiply(ptsNorm, scaleFactor)

    normMatrixInv = np.array([
        [1 / scaleFactor, 0, 0],
        [0, 1 / scaleFactor, 0],
        [cent[0], cent[1], 1]])

    return ptsNorm, normMatrixInv


def findProjectiveTransform(uv, xy):

    """
    This code is a Python implementation of Matlab code
    
    'findProjectiveTransform' in 'fitgeotrans' 
    
    Reference : to-be added here
    
    """
        
    uv, normMatrix1 = normalizeControlPoints(uv);
    xy, normMatrix2 = normalizeControlPoints(xy);

    minRequiredNonCollinearPairs = 4;
    M = xy.shape[0]
    x = xy[:, 0][:, np.newaxis]
    y = xy[:, 1][:, np.newaxis]
    vec_1 = np.ones((M, 1))
    vec_0 = np.zeros((M, 1))
    u = uv[:, 0][:, np.newaxis]
    v = uv[:, 1][:, np.newaxis]

    U = np.vstack([u, v])
    X = np.hstack([[x, y, vec_1, vec_0, vec_0, vec_0, np.multiply(-u, x), np.multiply(-u, y)],
                   [vec_0, vec_0, vec_0, x, y, vec_1, np.multiply(-v, x), np.multiply(-v, y)]]).squeeze().T

    # We know that X * Tvec = U
    if np.linalg.matrix_rank(X) >= 2 * minRequiredNonCollinearPairs:
        Tvec = np.linalg.lstsq(X, U, rcond=-1)[0]
    #     else :
    #         error(message('images:geotrans:requiredNonCollinearPoints', minRequiredNonCollinearPairs, 'projective'))

    #      We assumed I = 1;
    Tvec = np.append(Tvec, 1)
    Tinv = np.reshape(Tvec, (3, 3));

    Tinv = np.linalg.lstsq(normMatrix2, np.matmul(Tinv, normMatrix1), rcond=-1)[0]
    T = np.linalg.inv(Tinv)
    T = T / T[2, 2]

    return T

def getGrayImage(img) : 
   

    N = img.ndim
    if N == 3 : # If RGB Image, 
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if img.dtype == np.uint8:    
            img = np.asarray(img, dtype = np.float)/255
    elif N == 2: 
        if img.dtype == np.uint8:    
            img = np.asarray(img, dtype = np.float)/255
    return img 


def imgradient(img): 
    # 하드 코딩 : Matlab Sobel Filter
    hy = -np.asarray([[1.0, 2.0, 1.0], [0, 0, 0], [-1.0, -2.0, -1.0]])
    hx = hy.T
    
    Gx = convolve(img, hx, mode='nearest')
    Gy = convolve(img, hy, mode='nearest')
    
    gradientImg = np.hypot(Gx, Gy);
        
    return Gx, Gy, gradientImg


def getEdgePixels(gradientImg, edgeThresh): 
    Gmax = np.max(gradientImg[:])
    
    if not edgeThresh :
        # Python cv2 doen't take float image for otsu, 
        # Thus, we convert it into np.uint8 for thresholding for a while 
        edgeThresh, _ = cv2.threshold(np.asarray(gradientImg/Gmax*255, dtype=np.uint8),0,255, cv2.THRESH_OTSU)
        edgeThresh = edgeThresh/255

    t = Gmax * edgeThresh
    Ey, Ex = np.nonzero(gradientImg > t)

    return Ex, Ey


def bsxfun_1d(row, col, mode = 'times') : 
    
    mat_from_row = matlib.repmat(row, col.shape[0], 1)
    mat_from_col = matlib.repmat(col, row.shape[0], 1).T
    
    if mode == 'times':
        mat = np.multiply(mat_from_row, mat_from_col)
        
    elif mode == 'plus':
        mat = mat_from_row + mat_from_col
    
    return mat


def accum(accmap, a, size=None ): 
    
    if not size : 
        result = np.zeros((np.max(accmap[:, 0]), np.max(accmap[:, 1])), dtype=np.complex_) 
    
    else :
        result = np.zeros(size, dtype=np.complex_) 
        
    a = a[:, np.newaxis]
    concat = np.hstack((accmap, a))
    concat = concat[concat[:, 0].argsort()] # 이에 대해 sort
    
    df = pd.DataFrame(concat)
    x = df.groupby([0, 1]).sum().reset_index()[range(3)] #range(5) adjusts ordering 
    
    x_0 = np.asarray(x[0], dtype = np.int64) - 1
    x_1 = np.asarray(x[1], dtype = np.int64) - 1

    result[x_1, x_0] = x[2]    
    
    return result


def chaccum(A, radiusRange, method = 'phasecode',  objPolarity = 'bright', edgeThresh = [] ) : 
    
    maxNumElemNHoodMat = 1e6

    # all(A(:) == A(1));
    # Assume that image is not flat 

    # Get the input image in the correct format
    A = getGrayImage(A);

    ## Calculate gradient
    Gx, Gy, gradientImg = imgradient(A);

    Ex, Ey = getEdgePixels(gradientImg, edgeThresh);
    E = np.stack((Ey, Ex))

    # Not sure np.ravel_multi_index is equivalent with Matlab Function sub2ind
    idxE = np.ravel_multi_index(E, tuple(gradientImg.shape), mode='raise', order='C') 
    
    # Adding 0.0001 is to include end point of the radius
    radiusRange = np.arange(radiusRange[0], radiusRange[1]+0.0001, 0.5)

    if objPolarity == 'bright' :
        RR = radiusRange
    elif objPolarity == 'dark' :
        RR = - radiusRange

    ### This implementation only includes 'phasecode' mode 

    lnR = np.log(radiusRange);
    phi = ((lnR - lnR[0])/(lnR[-1] - lnR[0])*2*np.pi) - np.pi; # Modified form of Log-coding from Eqn. 8 in [3]

    Opca = np.exp(np.sqrt(-1+0j)*phi);
    w0 = Opca/(2*np.pi*radiusRange);

    xcStep = int(maxNumElemNHoodMat//RR.shape[0])

    lenE = Ex.shape[0]
    M, N = A.shape[0], A.shape[1]
    accumMatrix = np.zeros((M,N))
    
    for i in range(0, lenE+1, xcStep) : 
        
        
        Ex_chunk = Ex[i:int(np.min((i+xcStep-1,lenE)))]
        Ey_chunk = Ey[i:int(np.min((i+xcStep-1,lenE)))]
        idxE_chunk = idxE[i:int(np.min((i+xcStep-1,lenE)))]
        

        chunckX = np.divide(Gx[np.unravel_index(idxE_chunk, Gx.shape, 'C')],
                  gradientImg[np.unravel_index(idxE_chunk, gradientImg.shape, 'C')])

        chunckY = np.divide(Gy[np.unravel_index(idxE_chunk, Gy.shape, 'C')],
                  gradientImg[np.unravel_index(idxE_chunk, gradientImg.shape, 'C')])
        
        # Eqns. 10.3 & 10.4 from Machine Vision by E. R. Davies
        xc = matlib.repmat(Ex_chunk, RR.shape[0], 1).T + bsxfun_1d(-RR, chunckX) 
        yc = matlib.repmat(Ey_chunk, RR.shape[0], 1).T + bsxfun_1d(-RR, chunckY)

        xc = np.round(xc)
        yc = np.round(yc)

        w = matlib.repmat(w0, xc.shape[0], 1)

        ## Determine which edge pixel votes are within the image domain
        # Record which candidate center positions are inside the image rectangle.
        M, N = A.shape[0], A.shape[1]

        inside = (xc >= 1) & (xc <= N) & (yc >= 1) & (yc < M)
        # Keep rows that have at least one candidate position inside the domain.
        rows_to_keep = np.any(inside, 1);
        xc = xc[rows_to_keep,:];
        yc = yc[rows_to_keep,:];
        w = w[rows_to_keep,:];
        inside = inside[rows_to_keep,:];

        ## Accumulate the votes in the parameter plane
        xc = xc[inside]
        yc = yc[inside]

        xyc = np.asarray(np.stack((xc[:], yc[:])), dtype= np.int64)

        accumMatrix = accumMatrix + accum(xyc.T, w[inside], size=[M, N])

        del xc, yc, w # These are cleared to create memory space for the next loop. Otherwise out-of-memory at xc = bsxfun... in the next loop.
    
    return accumMatrix, gradientImg



def chcenters(accumMatrix, accumThresh) : 
    suppThreshold = accumThresh
    medFiltSize = 5
    kernel = np.ones((medFiltSize, medFiltSize),np.float32)/medFiltSize**2
    Hd = cv2.filter2D(accumMatrix,-1,kernel)

    suppThreshold = np.max(suppThreshold - np.spacing(suppThreshold), 0)
   

    Hd = reconstruction(Hd-suppThreshold, Hd, method ='dilation')

    lm = scipy.ndimage.filters.maximum_filter(Hd, size=3)
    bw = lm > np.max(lm)/3
    label_bw = label(bw)

    s = regionprops_table(label_bw, properties=['label','centroid'])
    centers = np.stack((s['centroid-0' ], s['centroid-1']))
    
    centers_int = np.asarray(centers, dtype = np.int64)
    metric = Hd[centers_int[0], centers_int[1]]
    
    # Sort the centers in descending order of metric    
    
    metric_sorted=np.sort(metric)[::-1]
    sortIndx=np.argsort(metric) 
    centers_sorted = np.fliplr(np.stack((np.take(centers[0,:], sortIndx), np.take(centers[1,:], sortIndx))))
    
    return np.flipud(centers_sorted), metric_sorted


def chradiiphcode(centers, accumMatrix, radiusRange) :
    centers_int = np.asarray(centers, dtype = np.int64)
    cenPhase = np.angle(accumMatrix[centers_int[1], centers_int[0]])
    lnR = np.log(radiusRange);
    
    # Inverse of modified form of Log-coding from Eqn. 8 in [1]
    r_estimated = np.exp(((cenPhase + np.pi)/(2*np.pi)*(lnR[-1] - lnR[0])) + lnR[0]) 
    
    return r_estimated


def imfindcircles(A, radiusRange,  ObjectPolarity = 'bright', sensitivity = 0.95):
    
    

    [accumMatrix, gradientImg] = chaccum(A, radiusRange, objPolarity=ObjectPolarity);

    ## Estimate the centers
    accumThresh = 1 - sensitivity;

    accumMatrix = abs(accumMatrix);

    centers, metric = chcenters(accumMatrix, accumThresh)

    ## Assume Image is flat 
    ## Currently, Sigma is not specified 
    idx2Keep = np.nonzero(metric >= accumThresh)
    centers = centers[:, idx2Keep]
    metric = metric[idx2Keep]

    r_estimated = chradiiphcode(centers, accumMatrix, radiusRange)
    
    return centers, r_estimated, metric



def circle_detection_multi_thread(img_name, param_config):
    sensor_num = str(os.path.basename(img_name)[4:7])
    params = param_config[sensor_num]
    img = imread(img_name)
    sensitivity = params['sensitivity']
    centers, r_estimated, metric = imfindcircles(img, 
                                         [params['min_rad'], params['max_rad']],
                                        sensitivity = sensitivity)
    circles = np.concatenate((centers, r_estimated[:,np.newaxis]), axis = 0).T
    circles = np.squeeze(circles)
    return circles