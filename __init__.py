from invoke import Collection
import utils
import scm

ns = Collection()
ns.add_collection(Collection.from_module(utils))
ns.add_collection(Collection.from_module(scm))
