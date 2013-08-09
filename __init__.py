from invoke import Collection

from . import utils
from . import scm

ns = Collection()
ns.add_collection(Collection.from_module(utils))
ns.add_collection(Collection.from_module(scm))
