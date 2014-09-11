from rpython.rlib             import jit
from small_list               import inline_small_list
from pycket.error             import SchemeException


class SymList(object):
    _immutable_fields_ = ["elems[*]", "prev"]
    def __init__(self, elems, prev=None):
        assert isinstance(elems, list)
        self.elems = elems
        self.prev = prev

    def check_plausibility(self, env):
        if self.elems:
            assert len(self.elems) == env._get_size_list()
        if self.prev:
            self.prev.check_plausibility(env.get_prev(self))

    @jit.unroll_safe
    def find_env_in_chain_speculate(self, target, env_structure, env):
        """
        find env 'target' of shape 'self' in environment chain 'env', described
        by 'env_structure'. We use the env structures to check for candidates
        of sharing. Only if the env structure that the lambda is defined in
        matches some outer env structure where it is called does it make sense
        to check if the *actual* envs match. this means that the speculation is
        essentially free:
        the env structures are known, so checking for sharing inside them is
        computed by the JIT. thus only an environment identity check that is
        very likely to succeed is executed.
        """
        jit.promote(self)
        jit.promote(env_structure)
        while env_structure is not None:
            if env_structure is self:
                if env is target:
                    return env
            env = env.get_prev(env_structure)
            env_structure = env_structure.prev
        return target


class ModuleEnv(object):
    _immutable_fields_ = ["modules", "toplevel_env"]
    def __init__(self, toplevel_env):
        self.modules = {}
        self.current_module = None
        self.toplevel_env = toplevel_env

    def require(self, module_name):
        assert 0
        # load the file, evaluate it, register it in the table

    def add_module(self, name, module):
        from pycket.interpreter import Module
        # note that `name` and `module.name` are different!
        assert isinstance(module, Module)
        self.modules[name] = module

    @jit.elidable
    def _find_module(self, name):
        return self.modules.get(name, None)


class Env(object):
    _immutable_fields_ = ["toplevel_env", "module_env"]
    _attrs_ = ['toplevel_env']

    def get_prev(self, env_structure):
        assert env_structure.elems == []
        return self


class Version(object):
    pass


class ToplevelEnv(Env):
    _immutable_fields_ = ["version?", "module_env", "toplevel_env"]
    def __init__(self):
        self.bindings = {}
        self.version = Version()
        self.toplevel_env = self # bit silly
        self.module_env = ModuleEnv(self)
        self.commandline_arguments = []

    def lookup(self, sym, env_structure):
        raise SchemeException("variable %s is unbound" % sym.variable_name())

    def toplevel_lookup(self, sym):
        from pycket.values import W_Cell
        jit.promote(self)
        w_res = self._lookup(sym, jit.promote(self.version))
        if isinstance(w_res, W_Cell):
            w_res = w_res.get_val()
        return w_res

    @jit.elidable
    def _lookup(self, sym, version):
        try:
            return self.bindings[sym]
        except KeyError:
            raise SchemeException("toplevel variable %s not found" % sym.variable_name())

    def toplevel_set(self, sym, w_val):
        from pycket.values import W_Cell
        if sym in self.bindings:
            self.bindings[sym].set_val(w_val)
        else:
            self.bindings[sym] = W_Cell(w_val)
            self.version = Version()


@inline_small_list(immutable=True, attrname="vals", factoryname="_make")
class ConsEnv(Env):
    _immutable_fields_ = ["_prev", "toplevel_env"]
    def __init__ (self, prev, toplevel):
        self.toplevel_env = toplevel
        self._prev = prev

    @staticmethod
    def make(vals, prev, toplevel):
        if vals:
            return ConsEnv._make(vals, prev, toplevel)
        return prev

    @jit.unroll_safe
    def lookup(self, sym, env_structure):
        jit.promote(env_structure)
        for i, s in enumerate(env_structure.elems):
            if s is sym:
                v = self._get_list(i)
                assert v is not None
                return v
        prev = self.get_prev(env_structure)
        return prev.lookup(sym, env_structure.prev)

    @jit.unroll_safe
    def set(self, sym, val, env_structure):
        jit.promote(env_structure)
        for i, s in enumerate(env_structure.elems):
            if s is sym:
                self._set_list(i, val)
                return
        prev = self.get_prev(env_structure)
        return prev.set(sym, val, env_structure.prev)

    def get_prev(self, env_structure):
        jit.promote(env_structure)
        if env_structure.elems:
            return self._prev
        return self

