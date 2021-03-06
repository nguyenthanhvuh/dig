import z3
import ast
import pdb
import operator

import helpers.vcommon as CM
import settings

DBG = pdb.set_trace

mlog = CM.getLogger(__name__, settings.logger_level)


class Z3:
    zTrue = z3.BoolVal(True)
    zFalse = z3.BoolVal(False)

    @classmethod
    def _and(cls, fs):
        assert isinstance(fs, list), fs

        if not fs:
            return None
        if len(fs) == 1:
            return fs[0]

        return z3.And(fs)

    @classmethod
    def is_var(cls, v):
        return z3.is_const(v) and v.decl().kind() == z3.Z3_OP_UNINTERPRETED

    @classmethod
    def _get_vars(cls, f, rs):
        """
        Helper method to obtain variables from a formula f recursively.
        Results are stored in the list rs.
        """
        assert z3.is_expr(f) or z3.is_const(f), f
        if z3.is_const(f):
            if cls.is_var(f):
                rs.add(f)
        else:
            for c in f.children():
                cls._get_vars(c, rs)

    @classmethod
    # @cached_function
    def get_vars(cls, f):
        """
        sage: from helpers.miscs import Z3
        sage: import z3
        sage: x,y,z = z3.Ints("x y z")
        sage: assert(Z3.get_vars(z3.And(x + y == z , y + z == z)) == {z, y, x})
        """
        assert z3.is_expr(f), f

        rs = set()
        cls._get_vars(f, rs)
        return frozenset(rs)

    @classmethod
    def create_solver(cls, maximize=False):
        assert isinstance(maximize, bool), maximize

        solver = z3.Optimize() if maximize else z3.Solver()
        solver.set(timeout=settings.SOLVER_TIMEOUT)
        solver.set("timeout", settings.SOLVER_TIMEOUT)
        return solver

    @classmethod
    def extract(self, models, f):
        assert (
            models is None
            or models is False
            or (
                isinstance(models, list)
                and all(isinstance(m, z3.ModelRef) for m in models)
                and models
            )
        ), models

        cexs = set()
        isSucc = models is not None
        if isSucc and models:  # disproved
            cexs = []
            for model in models:
                cex = {}
                for v in model:
                    mv = str(model[v])
                    try:
                        cex[str(v)] = mv if f is None else f(mv)
                    except SyntaxError:
                        # mlog.warning('cannot analyze {}'.format(model))
                        pass
                cexs.append(cex)
        return cexs, isSucc

    @classmethod
    def get_models(cls, f, k):
        """
        Returns the first k models satisfiying f.
        If f is not satisfiable, returns False.
        If f cannot be solved, returns None
        If f is satisfiable, returns the first k models
        Note that if f is a tautology, i.e., True, then the result is []
        """
        assert z3.is_expr(f), f
        assert k >= 1, k
        solver = cls.create_solver(maximize=False)
        solver.add(f)
        models = []
        i = 0
        while solver.check() == z3.sat and i < k:
            i = i + 1
            m = solver.model()
            if not m:  # if m == []
                mlog.warning("sat but no model")
                break
            models.append(m)
            # create new constraint to block the current model
            ands = []
            for v in m:
                try:
                    e = v() == m[v]
                except z3.Z3Exception:
                    """
                    when the model contains functions, e.g.,
                    [..., div0 = [(3, 2) -> 1, else -> 0]]
                    """
                    # mlog.warning('cannot analyze {}'.format(m))
                    pass

                ands.append(e)
            block = z3.Not(z3.And(ands))
            solver.add(block)

        stat = solver.check()

        if stat == z3.unknown:  # for z3.unknown/unsat/sat, use == instead of is
            rs = None
        elif stat == z3.unsat and i == 0:
            rs = False
        else:
            if models:
                rs = models
            else:
                # tmp fix,  ProdBin has a case when
                # stat is sat but model is []
                # so tmp fix is to treat that as unknown
                rs = None
                stat = z3.unknown

        # if (isinstance(rs, list) and not rs):
        #     print(f)
        #     print(k)
        #     print(stat)
        #     print(models)

        #     DBG()

        assert not (isinstance(rs, list) and not rs), rs
        return rs, stat

    @classmethod
    def is_proved(cls, claim):
        rs, stat = cls.get_models(claim, 1)
        return stat == z3.unsat

    @classmethod
    def imply(cls, fs, g):
        """
        sage: from helpers.miscs import Z3

        sage: var('x y')
        (x, y)
        sage: assert Z3.imply([x-6==0],x*x-36==0)
        sage: assert Z3.imply([x-6==0,x+6==0],x*x-36==0)
        sage: assert not Z3.imply([x*x-36==0],x-6==0)
        sage: assert not Z3.imply([x-6==0],x-36==0)
        sage: assert Z3.imply([x-7>=0], x>=6)
        sage: assert not Z3.imply([x-7>=0], x>=8)
        sage: assert not Z3.imply([x-6>=0], x-7>=0)
        sage: assert not Z3.imply([x-7>=0,y+5>=0],x+y-3>=0)
        sage: assert Z3.imply([x-7>=0,y+5>=0],x+y-2>=0)
        sage: assert Z3.imply([x-2*y>=0,y-1>=0],x-2>=0)
        sage: assert not Z3.imply([],x-2>=0)
        sage: assert Z3.imply([x-7>=0,y+5>=0],x+y-2>=0)
        sage: assert Z3.imply([x^2-9>=0,x>=0],x-3>=0)
        sage: assert Z3.imply([x-6==0],x*x-36==0)
        sage: assert not Z3.imply([x+7>=0,y+5>=0],x*y+36>=0)
        sage: assert not Z3.imply([x+7>=0,y+5>=0],x*y+35>=0)
        sage: assert not Z3.imply([x+7>=0,y+5>=0],x*y-35>=0)
        sage: assert not Z3.imply([x+7>=0],x-8>=0)
        sage: assert Z3.imply([x+7>=0],x+8>=0)
        sage: assert Z3.imply([x>=7,y>=5],x*y>=35)
        sage: assert not Z3.imply([x>=-7,y>=-5],x*y>=35)

        # sage: assert not Z3.imply([1/2*x**2 - 3/28*x + 1 >= 0],1/20*x**2 - 9/20*x + 1 >= 0,use_reals=True)
        # sage: assert Z3.imply([1/20*x**2 - 9/20*x + 1 >= 0],1/2*x**2 - 3/28*x + 1 >= 0,use_reals=True)
        # sage: assert Z3.imply([x+7>=0],x+8.9>=0,use_reals=True)

        """

        # assert all(Miscs.is_expr(f) for f in fs), fs
        # assert Miscs.is_expr(g), g

        if not fs:
            return False  # conservative approach
        # fs = [cls.toZ3(f, use_reals, use_mod=False) for f in fs]
        # g = cls.toZ3(g, use_reals, use_mod=False)

        fs = [Z3.parse(str(f)) for f in fs]
        g = Z3.parse(str(g))

        return cls._imply(fs, g)

    @classmethod
    def _imply(cls, fs, g, is_conj=True):
        assert z3.is_expr(g), g

        if is_conj:  # And(fs) => g
            if z3.is_expr(fs):
                claim = z3.Implies(fs, g)
            else:
                claim = z3.Implies(z3.And(fs), g)
        else:  # g => Or(fs)
            if z3.is_expr(fs):
                claim = z3.Implies(g, fs)
            else:
                claim = z3.Implies(g, z3.Or(fs))

        models, _ = cls.get_models(z3.Not(claim), k=1)
        return models is False

    @classmethod
    def parse(cls, node):
        """
        Parse sage expr to z3
        e.g., parse(str(sage_expr), use_reals=False)

        Note cannot parse something like tCtr == y - 1/2*sqrt(4*y**2 - 8*x + 4*y + 1) + 1/2
        """
        # print(ast.dump(node))

        if isinstance(node, str):
            node = node.replace("^", "**")

            tnode = ast.parse(node)
            tnode = tnode.body[0].value
            try:
                expr = cls.parse(tnode)
                expr = z3.simplify(expr)
                return expr
            except NotImplementedError:
                mlog.error(f"cannot parse: '{node}'\n{ast.dump(tnode)}")
                raise

        elif isinstance(node, ast.BoolOp):
            vals = [cls.parse(v) for v in node.values]
            op = cls.parse(node.op)
            return op(vals)

        elif isinstance(node, ast.And):
            return z3.And

        elif isinstance(node, ast.Or):
            return z3.Or

        elif isinstance(node, ast.BinOp):
            left = cls.parse(node.left)
            right = cls.parse(node.right)
            op = cls.parse(node.op)
            return op(left, right)

        elif isinstance(node, ast.UnaryOp):
            operand = cls.parse(node.operand)
            op = cls.parse(node.op)
            return op(operand)

        elif isinstance(node, ast.Compare):
            assert len(node.ops) == 1 and len(
                node.comparators) == 1, ast.dump(node)
            left = cls.parse(node.left)
            right = cls.parse(node.comparators[0])
            op = cls.parse(node.ops[0])
            return op(left, right)

        elif isinstance(node, ast.Name):
            return z3.Int(str(node.id))

        elif isinstance(node, ast.Num):
            return z3.IntVal(str(node.n))

        elif isinstance(node, ast.Add):
            return operator.add
        elif isinstance(node, ast.Mult):
            return operator.mul
        elif isinstance(node, ast.Div):
            return operator.truediv  # tvn:  WARNING: might not be accurate
        elif isinstance(node, ast.FloorDiv):
            return operator.truediv  # tvn:  WARNING: might not be accurate
        elif isinstance(node, ast.Mod):
            return operator.mod
        elif isinstance(node, ast.Pow):
            return operator.pow
        elif isinstance(node, ast.Sub):
            return operator.sub
        elif isinstance(node, ast.USub):
            return operator.neg
        elif isinstance(node, ast.Eq):
            return operator.eq
        elif isinstance(node, ast.NotEq):
            return operator.ne
        elif isinstance(node, ast.Lt):
            return operator.lt
        elif isinstance(node, ast.LtE):
            return operator.le
        elif isinstance(node, ast.Gt):
            return operator.gt
        elif isinstance(node, ast.GtE):
            return operator.ge

        else:
            raise NotImplementedError(ast.dump(node))

    @classmethod
    def simplify(cls, f):
        assert z3.is_expr(f), f
        simpl = z3.Tactic("ctx-solver-simplify")
        simpl = z3.TryFor(simpl, settings.SOLVER_TIMEOUT)
        try:
            f = simpl(f).as_expr()
        except z3.Z3Exception:
            pass
        return f

    @classmethod
    def to_smt2_str(cls, f, status="unknown", name="benchmark", logic=""):
        v = (z3.Ast * 0)()
        s = z3.Z3_benchmark_to_smtlib_string(
            f.ctx_ref(), name, logic, status, "", 0, v, f.as_ast()
        )
        return s

    @classmethod
    def from_smt2_str(cls, s):
        assertions = z3.parse_smt2_string(s)
        expr = cls.zTrue if not assertions else assertions[0]
        assert z3.is_expr(expr), expr
        return expr

    @classmethod
    def model_str(cls, m, as_str=True):
        """
        Returned a 'sorted' model by its keys.
        e.g. if the model is y = 3 , x = 10, then the result is
        x = 10, y = 3

        EXAMPLES:
        see doctest examples from function prove()

        """
        assert m is None or m == [] or isinstance(m, z3.ModelRef)

        if m:
            vs = [(v, m[v]) for v in m]
            vs = sorted(vs, key=lambda a: str(a[0]))
            if as_str:
                return '\n'.join(f"{k} = {v}" for (k, v) in vs)
            else:
                return vs
        else:
            return str(m) if as_str else m
