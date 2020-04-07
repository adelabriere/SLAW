import yaml
import numpy as np
import common.references as cr


def recur_node(x,path=None,all_args=None):
    if all_args is None:
        all_args = []
    if path is None:
        path = []
    if isinstance(x,dict) and "value" in x:
        return all_args.append(tuple(path))
    elif isinstance(x,dict):
        for k in x:
            recur_node(x[k],path+[k],all_args)
    else:
        pass

def get_all_parameters(ex):
    all_args=[]
    recur_node(ex,all_args=all_args)
    return all_args

def get_val(raw,path):
    if len(path)==0:
        return raw
    k = path[0]
    return get_val(raw[k],path[1:])

def set_val(raw,path,value,field="value"):
    if len(path)==0:
        raw[field]=value
        return
    k = path[0]
    set_val(raw[k],path[1:],value)


###Rabge parameters are handled internally by adding min and max in internal parameters.

class ParametersFileHandler:
    SEP = "__"
    SUFFIX_CONST = "const"
    SUFFIX_ADD = "add"

    def __init__(self,path=None):
        self.path=path
        with open(self.path, 'r') as stream:
            self.dic = yaml.safe_load(stream)
        self.param_path = get_all_parameters(self.dic)
        self.ranges=[]
        self.find_ranges()

    def __getitem__(self, item):
        if isinstance(item,str):
            item = item.split(ParametersFileHandler.SEP)
        return get_val(self.dic,item)

    def __setitem__(self, key, value):
        if isinstance(key,str):
            key = key.split(ParametersFileHandler.SEP)
        if key in self.ranges:
            value = [value[0],value[0]+value[1]]

        ###We check if is a range with two values.
        set_val(self.dic,key,value)

    def is_optimized(self):
        ##Cherck if the file has been optomized eventually
        return self.dic["optimized"]

    def find_ranges(self):
        for path in self.param_path:
            val = self[path]
            if isinstance(val["value"],list):
                self.ranges.append(path)

    def set_all_parameters(self,keys,values):
        keys = [tuple(k.split(ParametersFileHandler.SEP)) if isinstance(k,str) else tuple(k) for k in keys]
        dic_index = {k:idx for idx,k in enumerate(keys)}
        for d in dic_index.keys():
            try:
                if d[-1]==ParametersFileHandler.SUFFIX_CONST or d[-1]==ParametersFileHandler.SUFFIX_ADD:
                    prefix = d[:-1]
                    ###We look for the two terms in the
                    key_const = prefix + (ParametersFileHandler.SUFFIX_CONST,)
                    key_add = prefix + (ParametersFileHandler.SUFFIX_ADD,)
                    self[prefix]=(values[dic_index[key_const]],values[dic_index[key_add]])
                else:
                    self[d]=values[dic_index[d]]
            except KeyError:
                continue

    def get_optimizable_parameters(self,string=True):
        to_optimize = {}
        for path in self.param_path:
            val = self[path]
            if "range" in val:
                if path in self.ranges:
                    const_key = path+(ParametersFileHandler.SUFFIX_CONST,)
                    add_key = path+(ParametersFileHandler.SUFFIX_ADD,)
                    const_range = [val["range"]["min"][0],val["range"]["min"][1]]
                    min_fac = min(val["range"]["max"][0]-val["range"]["min"][0],
                                  val["range"]["max"][1]-val["range"]["min"][1])
                    max_fac = val["range"]["max"][1]-val["range"]["min"][0]
                    add_range = [min_fac,max_fac]
                    pconst = const_key
                    padd = add_key
                    if string:
                        pconst = ParametersFileHandler.SEP.join(pconst)
                        padd = ParametersFileHandler.SEP.join(padd)
                    else:
                        pconst = tuple(pconst)
                        padd = tuple(padd)
                    to_optimize[pconst]=const_range
                    to_optimize[padd]=add_range
                else:
                    ppath = path
                    if string:
                        ppath = ParametersFileHandler.SEP.join(ppath)
                    else :
                        ppath = tuple(path)
                    to_optimize[ppath]=val["range"]
        ###speicifically handle the range parameters
        return to_optimize

    def get_parameters(self,string=True):
        to_optim = self.get_optimizable_parameters(string=False)
        lpar = [pp for pp in self.param_path if pp not in self.ranges and pp not in to_optim]
        lapr = lpar + list(to_optim.keys())
        if string:
            return [ParametersFileHandler.SEP.join(pp) for pp in lpar]
        return lapr

    def write_parameters(self,path):
        with open(path, 'w') as outfile:
            yaml.dump(self.dic, outfile, default_flow_style=False)

if __name__=="__main__":
    PATH_PARAMS = "C:/Users/dalexis/Documents/dev/lcmsprocessing_docker/pylcmsprocessing/data/parameters_set.yaml"
    pfh = ParametersFileHandler(PATH_PARAMS)
    loptim = pfh.get_optimizable_parameters()
    lval = [(lb+ub)/2 for lb,ub in loptim.values()]
    lnames = list(loptim.keys())
    pfh.set_all_parameters(lnames,lval)
    pfh[('peakpicking', 'peaks_deconvolution', 'peak_width')]["value"]

    if pfh.is_optimized():
        print("To optimize")
    all_par = pfh.get_parameters(string=False)
    all_par_str = pfh.get_parameters()

    print("Old value  of ",all_par[2],"is",pfh[all_par[2]]["value"])
    pfh[all_par[2]] = 10
    print("New value  of ",all_par[2],"is",pfh[all_par[2]]["value"])
    pfh[all_par_str[2]] = 30
    print("New value with str  of ",all_par[2],"is",pfh[all_par[2]]["value"])
