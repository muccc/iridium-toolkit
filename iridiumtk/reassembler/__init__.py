import pkgutil
import importlib

def get_plugins(base_ns):
    _path=base_ns.__path__
    _name=base_ns.__name__

    return  {
        name[1+len(_name):]: importlib.import_module(name)
        for _, name, _
        in pkgutil.iter_modules(_path, _name + ".")
        if not name.startswith(_name + '._')
    }
