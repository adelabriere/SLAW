import math
import numpy as np
import inspect
import concurrent.futures

from model.optimization.rsm import bbdesign
from model.optimization.optimizer import rsmOptimizer,maxOptimizer

SAMPLER = ["random","bbd","lipo"]
def getSampler(name="lipo"):
    if name == "random":
        return uniformBoundedSampler
    elif name == "bbd":
        return bbdSampler
    elif name=="lipo":
        return lipoSampler
    return bbdSampler

OPTIMIZER = ["max","rsm"]
def getOptimizer(name="rsm"):
    if name=="rsm":
        return rsmOptimizer
    elif name=="max":
        return maxOptimizer
    return rsmOptimizer


class samplingOptimizer:
    def __init__(self,sampler,optimizer,bounds,fixed_arguments=None):
        if fixed_arguments is None:
            self.fixed_arguments = {}
        else:
            self.fixed_arguments = fixed_arguments
        self.bounds=bounds
        self.sampler=sampler
        self.optimizer=optimizer

    def optimize(self,func,num_points=100,relative_increase = 0.02,
                 max_its=3,contraction = 0.5, extension = 0.1,num_cores=1):
        ###We add some points
        global_best_point = None
        global_best_value = 0.01
        num_its = 0
        self.sampler.sample(bounds=self.bounds,func=func,num_cores=num_cores,num_points=num_points,fixed_arguments=self.fixed_arguments)
        current_best_point,current_best_value = self.optimizer.get_maximum(self.sampler.get_points(),self.sampler.get_values())
        first = True
        ###We always test the best point
        while first or (current_best_value-global_best_value)/global_best_value > (relative_increase) and num_its < max_its:
            first = False
            ###We restrain thge constraints using the newly determined best points
            self.bounds.contract_bound(current_best_point, contraction=contraction, extension=extension,
                                     extreme=0.02, only_positive=True)
            self.sampler.sample(bounds=self.bounds,func=func,num_cores=num_cores,num_points=num_points,fixed_arguments=self.fixed_arguments)
            current_best_point, current_best_value = self.optimizer.get_maximum(self.sampler.get_points(), self.sampler.get_values())
            if current_best_value>global_best_value:
                global_best_point = current_best_point
            num_its += 1

        ##We pick the bset sampled points
        all_values = self.sampler.get_values()
        all_points = self.sampler.get_points()
        pindex = all_values.index(max(all_values))
        return all_points[pindex,:]


class bounds:
    def __init__(self,lb,ub=None):
        if ub is None:
            self.ub = [x[0] for x in lb]
            self.lb = [x[1] for x in lb]
        else:
            self.ub = ub
            self.lb = lb

    def lower_bound(self):
        return self.lb

    def upper_bound(self):
        return self.ub

    def contract_bound(self,best_point, contraction=0.5, extension=0.1,
                                 extreme=0.02, only_positive=True):
        tnlb = [0.0] * len(self.lb)
        tnub = [0.0] * len(self.lb)
        crange = [(cub - clb) / 2 for cub, clb in zip(self.ub, self.lb)]

        for ip in range(len(self.lb)):
            nlb = best_point[ip] - crange[ip] * contraction
            nub = best_point[ip] + crange[ip] * contraction

            if (abs((best_point[ip] - self.lb[ip]) / crange[ip]) - 1) <= extreme:
                nlb = self.lb[ip] - crange[ip] * contraction * extension * 2
            else:
                if nlb < self.lb[ip]:
                    nlb = self.lb[ip]

            if (abs((best_point[ip] - self.ub[ip]) / crange[ip]) - 1) <= extreme:
                nub = self.ub[ip] + crange[ip] * contraction * extension * 2
            else:
                if nub > self.ub[ip]:
                    nub = self.ub[ip]

            if only_positive:
                if nlb < 0: nlb = 0

            tnlb[ip] = nlb
            tnub[ip] = nub
        self.lb = tnlb
        self.ub = tnub


class boundedSampler:
    def __init__(self):
        ###Self. point should be a list
        self.points = []
        self.values = []
        self.parallel=True

    ##This method jsut need to inherit the first one
    def sample(self,bounds,func,num_points=100,num_cores=1,fixed_arguments=None):
        points,values=self.sample_points(bounds,func,num_points,num_cores=num_cores,fixed_arguments=fixed_arguments)
        self.append_points(points,values)


    def append_points(self,points,values):
        self.points.append(points)
        self.values.append(values)

    def get_points(self):
        return np.concatenate(self.points)

    def get_values(self):
        return [y for x in self.values for y in x]

    def is_parallel(self):
        return self.parallel

#####################
## random sampling ##
#####################


def wrap_func_dic(x):
  func = x.pop("fun")
  ###We compute the function value
  return func(**x)



def do_uniform_random_sampling(lb,ub,func,num_points=1000,num_cores = None,fixed_arguments=None):
  '''
  :param constraints: a scipy.optimize.Bounds object
  :param func: The function ot be optimized
  :param max_call: The maximum number of call to the function allowed INCLUDING the initial points
  :param initial_points: The number of initial point sused for bounds estimation
  :return: The optimized paramters
  '''
  ###We give a signle core by parameters sets.

  if fixed_arguments is None:
    fixed_arguments = {}
  args_name = inspect.getfullargspec(func)[0]
  to_optimize = [name for name in args_name if name not in fixed_arguments]

  ##We read the dimension from the contraints
  ndim = len(lb)
  if len(to_optimize) != ndim:
    raise Exception("Arguments don't match.")

  val_par = [None]*ndim

  ###We just sample every parameters across the different
  for idx, (ilb,iub) in enumerate(zip(lb,ub)):
    par_seq = np.random.uniform(ilb, iub, num_points)
    val_par[idx] = par_seq

  ###We reshape the data frame in a list of dictionnary
  all_dict = [{**dict(zip(to_optimize, cargs)),**fixed_arguments,"fun":func} for cargs in zip(*val_par)]
  list_for_numpy = [cargs for cargs in zip(*val_par)]
  # vres = map(wrap_func_dic, all_dict)
  with concurrent.futures.ProcessPoolExecutor(max_workers=num_cores) as executor:
    vres = list(executor.map(wrap_func_dic, all_dict))

  ###We build a tuple of parameters
  np_table = np.array(list_for_numpy)
  return np_table,list(vres)

class uniformBoundedSampler(boundedSampler):
    def __init__(self):
        self.parallel=True
        super().__init__()

    def sample_points(self,limits,func,num_points,num_cores=None,fixed_arguments=None):
        points,values = do_uniform_random_sampling(limits.lower_bound(), limits.upper_bound(), func, num_points=num_points,
                                                   num_cores=num_cores, fixed_arguments=fixed_arguments)
        return points,values

##################
## BDD sampling ##
##################

def do_bbd(lb, ub, func, num_cores=1, fixed_arguments=None):
        '''
        :param constraints: a scipy.optimize.Bounds object
        :param func: The function ot be optimized
        :param max_call: The maximum number of call to the function allowed INCLUDING the initial points
        :param initial_points: The number of initial point sused for bounds estimation
        :return: The optimized paramters
        '''
        ###We count the number of arguments
        ###We give a signle core by parameters sets.

        if fixed_arguments is None:
            fixed_arguments = {}
        args_name = inspect.getfullargspec(func)[0]
        to_optimize = [name for name in args_name if name not in fixed_arguments]

        ##We read the dimension from the contraints
        ndim = len(lb)
        bbd = bbdesign(ndim, center=1)
        for it in range(ndim):
            bbd[:, it] = bbd[:, it] * (ub[it] - lb[it]) / 2 + (ub[it] + lb[it]) / 2
        lpar = bbd.tolist()
        print("Using ",num_cores," parameters")
        ###We reshape the data frame in a list of dictionnary
        all_dict = [{**dict(zip(to_optimize, cargs)), **fixed_arguments, "fun": func} for cargs in lpar]
        list_for_numpy = [cargs for cargs in zip(*lpar)]

        with concurrent.futures.ProcessPoolExecutor(max_workers=num_cores) as executor:
            vres = list(executor.map(wrap_func_dic, all_dict))
        # vres = list(map(wrap_func_dic, all_dict))
        np_table = np.array(list_for_numpy)
        return np_table.T,vres

class bbdSampler(boundedSampler):
    def __init__(self):
        self.parallel=True
        super().__init__()

    def sample_points(self,bounds,func,num_points,num_cores=1,fixed_arguments=None):
        points,values = do_bbd(bounds.lower_bound(), bounds.upper_bound() , func, num_cores=num_cores,
                               fixed_arguments=fixed_arguments)
        return points,values


###################
## LIPO sampling ##
###################

def upper_bound(x,supp):
  points, val_points, k = supp
  ###We strat by substracting the value of X to all elements of points
  diff_points = [p-x for p in points]
  m_diff_points = np.array(diff_points)

  ###We tranform k in a squre matrix
  pow_k = [kk**2 for kk in k]
  pow_k = np.diag(pow_k)

  ###We compute the k derived part
  k_term = np.sqrt(np.apply_along_axis(lambda x, k: np.matmul(np.matmul(x, k), x.T), 1, m_diff_points, k=pow_k))
  fun_values = k_term+val_points

  ###This return the value of the upper bound
  return -np.min(fun_values)

####The upper bound which is piecewise linear can be approximated easly.
def maximize_upper_bound(points,val_points,k,lbi,ubi):
  ndim = points.shape[1]
  max_point = [0]*ndim
  ##We find the best coo
  points = np.asarray(points)
  ndim = points.shape[1]
  npoints = points.shape[0]
  val_points=np.asarray(val_points)
  xorder = np.apply_along_axis(np.argsort,0,points).T
  for d in range(ndim):
    dxorder = xorder[d,:]
    dxorder = dxorder.astype("int_")
    ub = ubi[d]
    lb = lbi[d]
    ##Al the dimesnion values
    xval = points[dxorder,d]
    yval = val_points[dxorder]
    kval = k[d]
    sx = xval[0:(npoints-1)]+xval[1:npoints]
    dy = np.diff(yval)
    middle_x = 0.5*(dy/kval+sx)
    middle_y = yval[0:(npoints-1)]+(middle_x-xval[0:(npoints-1)])*kval

    ###We add the bound if necessary
    ##Lower bound
    if np.abs(xval[0]-lb) > 0.00001:
      middle_x = np.insert(middle_x,0,lb)
      nval = yval[0]+(xval[0]-lb)*kval

      ###We insert the indices at the first positon
      middle_y = np.insert(middle_y,0,nval)
    if (np.abs(xval[npoints-1] - ub) > 0.00001):
      middle_x = np.append(middle_x, ub)
      nval = yval[npoints-1]+(ub-xval[npoints-1])*kval
      middle_y = np.append(middle_y,nval)
    ###We fidn the index of the maximum middle point
    index = np.where(middle_y == np.amax(middle_y))
    ###We return the best candidate
    try:
      max_point[d]=middle_x[index].item()
    except ValueError:
      ##In this case we return None
      return None
  return max_point


def calculateLipschitzConstant(points,val_points):
  ###We calculate the highest slope sbetween neibouring point
  mpoints = np.asarray(points)
  ndim = mpoints.shape[1]
  xorder = np.apply_along_axis(np.argsort,0,mpoints).T
  val_points=np.asarray(val_points)
  k = [None]*ndim
  for d in range(ndim):
    dxorder = xorder[d,:]
    dxorder = dxorder.astype("int_")
    dy = np.diff(val_points[dxorder])
    dx = np.diff(mpoints[dxorder,d])
    slopes = np.abs(dy/dx)
    ###We take the maximu slopes as the possible slopes
    k[d]=np.max(slopes)
  return k

def do_lipo(lb,ub,func,max_call=50,initial_points = 3,fixed_arguments=None):
  '''
  :param constraints: a scipy.optimize.Bounds object
  :param func: The function ot be optimized
  :param max_call: The maximum number of call to the function allowed INCLUDING the initial points
  :param initial_points: The number of initial point sused for bounds estimation
  :return: The optimized paramters
  '''
  ###We count the number of arguments
  if fixed_arguments is None:
    fixed_arguments = {}
  args_name = inspect.getfullargspec(func)[0]
  to_optimize = [name for name in args_name if name not in fixed_arguments]

  ##We read the dimension from the contraints
  ndim = len(lb)
  if len(to_optimize) != ndim:
    raise Exception("Arguments don't match.")

  counter = 0
  vpar = [None]*ndim
  ###We sample each paraneters across the different dimension
  for idx, (ilb,iub) in enumerate(zip(lb,ub)):
    par_seq = np.linspace(ilb, iub, 2*initial_points+1)
    par_seq=par_seq[range(1,2*initial_points+1,2)]
    vpar[idx] = par_seq

  ###We initialize the points matrix
  points = np.array(vpar).T
  counter += initial_points
  points = np.append(points, [[0.0]*ndim]*(max_call-counter), axis=0)

  val_points=[0.0]*initial_points

  def wrap_func(x,min_names,fixed):
    dict_min = dict(zip(min_names,x))
    dict_call = {**dict_min,**fixed}
    ###We compute the function value
    return func(**dict_call)

  for ip in range(len(val_points)):
    # dict_call = dict(zip(nn,points[ip,:]))
    ##We add the fixed arugments.
    val_points[ip] = wrap_func(points[ip,:],to_optimize,fixed_arguments)

  ###Computing the intiali Lipshictz constant function
  k =calculateLipschitzConstant(points[range(counter),:],val_points)
  while counter < max_call:
    ###we start by finding a first minimization point
    x0 = [0.0] * ndim
    ###We sample the inital k values
    new_point = maximize_upper_bound(points[range(counter),:], val_points, k, lb,ub)
    ###if the returned point is None it s that we already found an upper boud.
    if new_point is None:
      counter -= 1
      break
    ###If the point is already present
    val_new_point = wrap_func(new_point,to_optimize,fixed_arguments)
    val_points.append(val_new_point)
    points[counter,:] = new_point
    ##We recompute the Lipschitz constant evnetually
    counter += 1
    k = calculateLipschitzConstant(points[range(counter),:], val_points)
  ###We just have oto return the best values now
  return points[range(counter),:],[val_points[iv] for iv in range(counter)]


class lipoSampler(boundedSampler):
    def __init__(self):
        self.parallel=False
        super().__init__()

    def sample_points(self,bounds,func,num_points,num_cores=None,fixed_arguments=None):
        points,values = do_lipo(bounds.lower_bound(), bounds.upper_bound() , func,max_call=num_points,
                                initial_points = 4, fixed_arguments=fixed_arguments)
        return points,values


if __name__=="__main__":
    lb=[-1.5,-2.5,0.05]
    ub=[3.5,2.5,10]
    def test(x,y,z,k,e):
        return e*(-5*(10*(x+y*z)+2*(x+y)**2)+k+3*z**2+0.5*z*x)
    ob = bounds(lb,ub)
    bbsampler = bbdSampler()
    rsm_optimizer = rsmOptimizer()
    sO = samplingOptimizer(bbsampler,rsm_optimizer,ob,fixed_arguments={"k":3,"e":-100})
    best_point_O = sO.optimize(test,max_its=20,extension=0.0)
    to_call_bbd = list(best_point_O)+[3,-100]

    uob = bounds(lb,ub)
    rsample = uniformBoundedSampler(num_points=bbdesign(3).shape[0])
    sU = samplingOptimizer(rsample,rsm_optimizer,uob,fixed_arguments={"k":3,"e":-100})
    best_point = sU.optimize(test,extension=0.0)
    to_call_unif = list(best_point)+[3,-100]

    lob = bounds(lb,ub)
    lipo_sampler = LIPOSampler(num_points=bbdesign(3).shape[0])
    sLIPO = samplingOptimizer(lipo_sampler,rsm_optimizer,lob,fixed_arguments={"k":3,"e":-100})
    best_point = sLIPO.optimize(test,extension=0.0)
    to_call_lipo = list(best_point)+[3,-100]
    def wfun(args,k,e):
        x, y, z = args
        return -test(x,y,z,k,e)

    from scipy.optimize import minimize,Bounds
    bb = Bounds(lb,ub)
    rop = scipy.optimize.minimize(wfun,x0=(1,1,5), args=(3,-100),method="L-BFGS-B", bounds=bb )
    largs = list(rop.x)+[3,-100]
    print("optim: ",test(*largs),largs)
    print("bbd: ",test(*to_call_bbd),to_call_bbd)
    print("random: ",test(*to_call_unif),to_call_unif)
    print("lipo: ", test(*to_call_lipo), to_call_lipo)