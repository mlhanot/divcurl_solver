from dolfin import *
import numpy as np

class BiotSavart_harmonic:
    """
    Set DBC to true to solve with essential boundary condition
    Set Elemdict to override default elem, dictionary of the form {0f : {form : 'trimmed', degree : 1},1f ... }, trimmed and full are supported. No check are performed to ensure coherency of degrees.
    First call init_mesh(mesh,search_harmonics=True,expected_harmonics=2,printvp=False,customthreshold=1e-15,imported=None) 
         search_harmonics take time and should be disable when the domain is simply connected
         Custom parameter may be passed to the solver by editing the dictionnary "Tunning" before calling this function
         customthreshold set the value at which a singular value (or eigen value) is treated as 0, set printvp to display found value.
         imported may be used to restaure computed harmonics, the format is :{'n' : self.n1,'fh1' : self.fh1}
         It can be generated by export_harmonic(). fh1 is an array of lenght n of Function on the harmonic space.
         Beware that harmonics depends greatly on mesh, they shouldn't be imported from a mesh with different raffinement and also depend on the boundary condition. Use this with care as no check are implemented and incorrect data will silently corrupt the solver.
         The safest way to export might be to save in a file rather than using pickle and also get the mesh from the same file.
    
    Supported option for Tunning are :
    Tunning["solver"] == "SLEPc_SVD", "SuiteSparse_QR", "Scipy_eigs"
        When using "SLEPc_SVD", Tunning["ncv"] and Tunning["mpd"] dictate to corresponding parameter in the library (when both are set at the same time, else they are ignored).
        When using "Scipy_eigs" Tunning["eigs_tol"] is available (ncv is also supported by the algorithm but the warpper isn't done yet, this should be easy to add).
    
    Set fe0 and fe2 to desired value
    Call interpolate()
    Then all solve variant are available
    solve() return a function in the mixed space
    solve_1_form_dual() return a vector field
    """
    def __init__(self,DBC=False,Elemdict = {
        '0f' : {'form' : 'trimmed', 'degree' : 1}, '1f' : {'form' : 'trimmed', 'degree' : 1}, 
        '2f' : {'form' : 'trimmed', 'degree' : 1}}):
        
        self.Elemdict = Elemdict
        if (Elemdict['0f']['form'] == 'trimmed'):
            self.Elemf0 = FiniteElement('P-', cell='triangle', degree=Elemdict['0f']['degree'], form_degree=0)
        elif (Elemdict['0f']['form'] == 'full'):
            self.Elemf0 = FiniteElement('P', cell='triangle', degree=Elemdict['0f']['degree'], form_degree=0)
        else:
            print("Form {} not supported".format(Elemdict['0f']['form']))
        if (Elemdict['1f']['form'] == 'trimmed'):
            self.Elemf1 = FiniteElement('P-', cell='triangle', degree=Elemdict['1f']['degree'], form_degree=1)
        elif (Elemdict['1f']['form'] == 'full'):
            self.Elemf1 = FiniteElement('P', cell='triangle', degree=Elemdict['1f']['degree'], form_degree=1)
        else:
            print("Form {} not supported".format(Elemdict['1f']['form']))
        if (Elemdict['2f']['form'] == 'trimmed'):
            self.Elemf2 = FiniteElement('P-', cell='triangle', degree=Elemdict['2f']['degree'], form_degree=2)
        elif (Elemdict['2f']['form'] == 'full'):
            self.Elemf2 = FiniteElement('P', cell='triangle', degree=Elemdict['2f']['degree'], form_degree=2)
        else:
            print("Form {} not supported".format(Elemdict['2f']['form']))
        self.PH = FiniteElement('Real', cell='triangle', degree=0) # space of harmonic form (constant 0 form here)
        
        self.fe0 = Expression("0", degree=2)
        self.fe1 = Expression(("0.","0."), degree=2)
        self.fe2 = Expression("0", degree=2)
        
        self.DBC = DBC
        self.Tunning = {}
    
    def export_harmonic(self):
        return {'n' : self.n1,'fh1' : self.fh1}
    # could probably be improved but defined this way to keep compatibility
    def import_harmonic(self,harmonics):
        self.n1 = harmonics['n']
        Lu1 = []
        for i in range(self.n1):
            Lu1.append(project(harmonics['fh1'][i], self.F1))
        return Lu1
    def init_mesh(self,mesh,search_harmonics=False,expected_harmonics=2,printvp=False,customthreshold=1e-15,imported=None):
        self.mesh = mesh
        Lu1 = []
        if (search_harmonics):
            if imported is not None and 'n' in imported:
                self.n1 = imported['n']
            else:
                self.n1 = get_harmonic1_basis(self.mesh,Lu1,DBC=self.DBC,Elemdict=self.Elemdict,
                                              Tunning=self.Tunning,expected_harmonics=expected_harmonics,
                                              printvp=printvp,customthreshold=customthreshold)
        else:
            self.n1 = 0
        # We must postpone space definition as they now depend on mesh
        self.PH1 = []
        self.EPH1 = None
        self.TH = None
        if (self.n1 > 0):
            for i in range(self.n1):
                self.PH1.append(FiniteElement('Real', cell='triangle', degree=0)) #Hold coeff for basis of harmonic 1-forms
            self.EPH1 = MixedElement(self.PH1)
            self.TH = MixedElement([self.Elemf0,self.Elemf1,self.Elemf2,self.PH,self.EPH1])
        else:
            self.TH = MixedElement([self.Elemf0,self.Elemf1,self.Elemf2,self.PH])
        #
        self.W = FunctionSpace(self.mesh, self.TH)
        self.F0 = FunctionSpace(self.mesh,self.Elemf0)
        self.F1 = FunctionSpace(self.mesh,self.Elemf1)
        self.F2 = FunctionSpace(self.mesh,self.Elemf2)
        self.FPH = FunctionSpace(self.mesh,self.PH)
        self.FPH1 = None
        if (self.n1 > 0):
            self.FPH1 = FunctionSpace(self.mesh,self.EPH1)
        self.f = Function(self.W)
        self.fh1 = []
        for i in range(self.n1):
            self.fh1.append(Function(self.F1))
        if imported is not None:
            Lu1 = self.import_harmonic(imported)
        self.set_harmonic_basis(Lu1)
        self.dbc = []
        if (self.DBC):
            (self.a,self.L) = self.set_problem_DBC(self.W,self.f,self.fh1)
            self.dbc = [DirichletBC(self.W.sub(0), Constant(0.), boundary_whole),
                                           DirichletBC(self.W.sub(1), Constant((0.,0.)), boundary_whole)]
        else:
            (self.a,self.L) = self.set_problem(self.W,self.f,self.fh1)
        self.assigner = None
        self.fah1 = None
        if (self.n1 > 0):
            self.assigner = FunctionAssigner(self.W, [self.F0, self.F1, self.F2, self.FPH, self.FPH1])
            self.fah1 = Function(self.FPH1)
        else:
            self.assigner = FunctionAssigner(self.W, [self.F0, self.F1, self.F2, self.FPH])
        self.fa0 = Function(self.F0)
        self.fa1 = Function(self.F1)
        self.fa2 = Function(self.F2)
        self.fah = Function(self.FPH)
        
        
    def interpolate(self):
        self.fa0.interpolate(self.fe0)
        self.fa1.interpolate(self.fe1)
        self.fa2.interpolate(self.fe2)
        if (self.n1 > 0):
            self.assigner.assign(self.f, [self.fa0, self.fa1, self.fa2, self.fah, self.fah1])
        else:
            self.assigner.assign(self.f, [self.fa0, self.fa1, self.fa2, self.fah])
    
    def set_harmonic_basis(self,u):
        for i in range(self.n1):
            self.fh1[i].assign(u[i])
    
    def solve(self):
        usol = Function(self.W)
        solve(self.a == self.L,usol,self.dbc)
        return usol
    
    def solve_1_form_dual(self):
        usol = Function(self.W)
        solve(self.a == self.L,usol,self.dbc)
        B = project(as_vector((usol.sub(1)[1],-usol.sub(1)[0])), self.F1)
        return B
    
    def set_problem(self,W,f,fh1):
        if (self.n1 >0):
            (u_0,u_1,u_2,u_p,u_p1) = TrialFunctions(W)
            (v_0,v_1,v_2,v_q,v_q1) = TestFunctions(W)
            (f_0,f_1,f_2,f_h,f_h1) = split(f)
        else:
            (u_0,u_1,u_2,u_p) = TrialFunctions(W)
            (v_0,v_1,v_2,v_q) = TestFunctions(W)
            (f_0,f_1,f_2,f_h) = split(f)
        a1 = u_0.dx(0)*v_1[0]*dx + u_0.dx(1)*v_1[1]*dx + (u_1[1].dx(0) - u_1[0].dx(1))*v_2*dx
        a2 = v_0.dx(0)*u_1[0]*dx + v_0.dx(1)*u_1[1]*dx + (v_1[1].dx(0) - v_1[0].dx(1))*u_2*dx
        ah = u_p*v_0*dx + u_0*v_q*dx
        for i in range(self.n1):
            ah = ah + u_p1[i]*inner(fh1[i],v_1)*dx + v_q1[i]*inner(fh1[i],u_1)*dx
        a = a1 + a2 + ah
        L = f_0*v_0*dx + f_1[0]*v_1[0]*dx + f_1[1]*v_1[1]*dx + f_2*v_2*dx
        return (a,L)
    
    def set_problem_DBC(self,W,f,fh1):
        if (self.n1 >0):
            (u_0,u_1,u_2,u_p,u_p1) = TrialFunctions(W)
            (v_0,v_1,v_2,v_q,v_q1) = TestFunctions(W)
            (f_0,f_1,f_2,f_h,f_h1) = split(f)
        else:
            (u_0,u_1,u_2,u_p) = TrialFunctions(W)
            (v_0,v_1,v_2,v_q) = TestFunctions(W)
            (f_0,f_1,f_2,f_h) = split(f)
        a1 = u_0.dx(0)*v_1[0]*dx + u_0.dx(1)*v_1[1]*dx + (u_1[1].dx(0) - u_1[0].dx(1))*v_2*dx
        a2 = v_0.dx(0)*u_1[0]*dx + v_0.dx(1)*u_1[1]*dx + (v_1[1].dx(0) - v_1[0].dx(1))*u_2*dx
        ah = u_p*v_2*dx + u_2*v_q*dx
        for i in range(self.n1):
            ah = ah + u_p1[i]*inner(fh1[i],v_1)*dx + v_q1[i]*inner(fh1[i],u_1)*dx
        a = a1 + a2 + ah
        L = f_0*v_0*dx + f_1[0]*v_1[0]*dx + f_1[1]*v_1[1]*dx + f_2*v_2*dx
        return (a,L)

class BiotSavart_harmonic_restrict:
    """
    As of now depreciated
    This version use a restricted space for trial and test function.
    Set DBC to true to solve with essential boundary condition
    First call init_mesh(mesh,search_harmonics=True) search_harmonics take time and should be disable when the domain is simply connected
    Set fe0 and fe2 to desired value
    Call interpolate()
    Then all solve variant are available
    solve() return a function in the mixed space
    solve_1_form_dual() return a vector field (does not work for now)
    solve_DBC() and solve_1_form_dual_DBC() solve for a essential boundary condition (does not work for now)
    """
    def __init__(self,DBC=False):
        
        self.Elemf0 = FiniteElement('P-', cell='triangle', degree=1, form_degree=0)
        self.Elemf1 = FiniteElement('P-', cell='triangle', degree=1, form_degree=1)
        self.Elemf2 = FiniteElement('P-', cell='triangle', degree=1, form_degree=2)
        self.PH = FiniteElement('Real', cell='triangle', degree=0) # space of harmonic form (constant 0 form here)
        
        self.fe0 = Expression("0", degree=2)
        self.fe2 = Expression("0", degree=2)
        
        self.DBC = DBC
        if(DBC):
            print("Dirichlet boundary not yet implemented")
            raise NotImplementedError
        
    def init_mesh(self,mesh,search_harmonics=True,printvp=False,customthreshold=1e-15):
        self.mesh = mesh
        Lu1 = []
        if (search_harmonics):
            # When using mixed BC care must be taken to determine harmonic forms as they are no longer linked to te surface genus
            self.n1 = get_harmonic1_basis_legacy(self.mesh,Lu1,self.DBC,printvp,customthreshold)
        else:
            self.n1 = 0
        # We must postpone space definition as they now depend on mesh
        self.PH1 = []
        for i in range(self.n1):
            self.PH1.append(FiniteElement('Real', cell='triangle', degree=0)) #Hold coeff for basis of harmonic 1-forms
        self.EPH1 = MixedElement(self.PH1)
        self.TH = MixedElement([self.Elemf0,self.Elemf1,self.Elemf2,self.PH,self.EPH1])
        # Asym
        self.TH1 = MixedElement([self.Elemf1,self.PH])
        self.TH2 = MixedElement([self.Elemf0,self.Elemf2,self.EPH1])
        #
        self.W = FunctionSpace(self.mesh, self.TH)
        self.W1 = FunctionSpace(self.mesh,self.TH1)
        self.W2 = FunctionSpace(self.mesh,self.TH2)
        self.F0 = FunctionSpace(self.mesh,self.Elemf0)
        self.F1 = FunctionSpace(self.mesh,self.Elemf1)
        self.F2 = FunctionSpace(self.mesh,self.Elemf2)
        self.FPH = FunctionSpace(self.mesh,self.PH)
        self.FPH1 = FunctionSpace(self.mesh,self.EPH1)
        self.f = Function(self.W2)
        self.fh1 = []
        for i in range(self.n1):
            self.fh1.append(Function(self.F1))
        self.set_harmonic_basis(Lu1)
        self.dbc = []
        if (self.DBC):
            (self.a,self.L) = self.set_problem_DBC(self.W1,self.W2,self.f,self.fh1)
            self.dbc = [DirichletBC(self.W2.sub(0), Constant(0.), boundary_whole),
                                           DirichletBC(self.W1.sub(0), Constant((0.,0.)), boundary_whole)]
        else:
            (self.a,self.L) = self.set_problem(self.W1,self.W2,self.f,self.fh1)
        self.assigner = FunctionAssigner(self.W2, [self.F0,  self.F2, self.FPH1])
        self.fa0 = Function(self.F0)
        self.fa2 = Function(self.F2)
        self.fah1 = Function(self.FPH1)
        
    def interpolate(self):
        self.fa0.interpolate(self.fe0)
        self.fa2.interpolate(self.fe2)
        self.assigner.assign(self.f, [self.fa0,  self.fa2,  self.fah1])
    
    def set_harmonic_basis(self,u):
        for i in range(self.n1):
            self.fh1[i].assign(u[i])
    
    def solve(self):
        usol = Function(self.W1)
        solve(self.a == self.L,usol,self.dbc)
        return usol
    
    def solve_1_form_dual(self):
        usol = Function(self.W1)
        solve(self.a == self.L,usol,self.dbc)
        B = project(as_vector((usol.sub(0)[1],-usol.sub(0)[0])), self.F1)
        return B
        
    def set_problem(self,W1,W2,f,fh1):
        (u_1,u_p) = TrialFunctions(W1)
        (v_0,v_2,v_q1) = TestFunctions(W2)
        (f_0,f_2,f_h1) = split(f)
        a1 = (u_1[1].dx(0) - u_1[0].dx(1))*v_2*dx
        a2 = v_0.dx(0)*u_1[0]*dx + v_0.dx(1)*u_1[1]*dx
        ah = u_p*v_0*dx 
        for i in range(self.n1):
            ah = ah + v_q1[i]*inner(fh1[i],u_1)*dx
        a = a1 + a2 + ah
        L = f_0*v_0*dx  + f_2*v_2*dx
        return (a,L)
    
    def set_problem_DBC(self,W1,W2,f,fh1):
        (u_1,u_p) = TrialFunctions(W1)
        (v_0,v_2,v_q1) = TestFunctions(W2)
        (f_0,f_2,f_h1) = split(f)
        a1 = (u_1[1].dx(0) - u_1[0].dx(1))*v_2*dx
        a2 = v_0.dx(0)*u_1[0]*dx + v_0.dx(1)*u_1[1]*dx
        ah = u_p*v_2*dx 
        for i in range(self.n1):
            ah = ah + v_q1[i]*inner(fh1[i],u_1)*dx
        a = a1 + a2 + ah
        L = f_0*v_0*dx  + f_2*v_2*dx
        return (a,L)

class BiotSavart_base:
    def __init__(self,DBC=False,Elemdict = {
        '0f' : {'form' : 'trimmed', 'degree' : 1}, '1f' : {'form' : 'trimmed', 'degree' : 1}, 
        '2f' : {'form' : 'trimmed', 'degree' : 1}}):
        
        if (Elemdict['0f']['form'] == 'trimmed'):
            self.Elemf0 = FiniteElement('P-', cell='triangle', degree=Elemdict['0f']['degree'], form_degree=0)
        elif (Elemdict['0f']['form'] == 'full'):
            self.Elemf0 = FiniteElement('P', cell='triangle', degree=Elemdict['0f']['degree'], form_degree=0)
        else:
            print("Form {} not supported".format(Elemdict['0f']['form']))
        if (Elemdict['1f']['form'] == 'trimmed'):
            self.Elemf1 = FiniteElement('P-', cell='triangle', degree=Elemdict['1f']['degree'], form_degree=1)
        elif (Elemdict['1f']['form'] == 'full'):
            self.Elemf1 = FiniteElement('P', cell='triangle', degree=Elemdict['1f']['degree'], form_degree=1)
        else:
            print("Form {} not supported".format(Elemdict['1f']['form']))
        if (Elemdict['2f']['form'] == 'trimmed'):
            self.Elemf2 = FiniteElement('P-', cell='triangle', degree=Elemdict['2f']['degree'], form_degree=2)
        elif (Elemdict['2f']['form'] == 'full'):
            self.Elemf2 = FiniteElement('P', cell='triangle', degree=Elemdict['2f']['degree'], form_degree=2)
        else:
            print("Form {} not supported".format(Elemdict['2f']['form']))
        self.PH = FiniteElement('Real', cell='triangle', degree=0) # space of harmonic form (constant 0 form here)
        self.TH = MixedElement([self.Elemf0,self.Elemf1,self.Elemf2,self.PH])
        self.fe0 = Expression("0", degree=2)
        self.fe1 = Expression(("0.","0."), degree=2)
        self.fe2 = Expression("0", degree=2)
        self.DBC = DBC
        
    def init(self,mesh):
        self.mesh = mesh
        self.W = FunctionSpace(self.mesh, self.TH)
        self.F0 = FunctionSpace(self.mesh,self.Elemf0)
        self.F1 = FunctionSpace(self.mesh,self.Elemf1)
        self.F2 = FunctionSpace(self.mesh,self.Elemf2)
        self.FPH = FunctionSpace(self.mesh,self.PH)
        self.f = Function(self.W)
        if (self.DBC):
            a, L = self.set_problem_DBC(self.W)
            A, b = assemble_system(a,L,[DirichletBC(self.W.sub(0), Constant(0.), boundary_whole),
                                           DirichletBC(self.W.sub(1), Constant((0.,0.)), boundary_whole)])
            return A
        else:
            a, L = self.set_problem(self.W)
            return assemble(a)
        
    def set_problem(self,W):
        (u_0,u_1,u_2,u_p) = TrialFunctions(W)
        (v_0,v_1,v_2,v_q) = TestFunctions(W)
        a1 = u_0.dx(0)*v_1[0]*dx + u_0.dx(1)*v_1[1]*dx + (u_1[1].dx(0) - u_1[0].dx(1))*v_2*dx
        a2 = v_0.dx(0)*u_1[0]*dx + v_0.dx(1)*u_1[1]*dx + (v_1[1].dx(0) - v_1[0].dx(1))*u_2*dx
        ah = u_p*v_0*dx + u_0*v_q*dx
        a = a1 + a2 + ah
        L = Constant(0.)*v_q*dx
        return (a,L)
    
    def set_problem_DBC(self,W):
        (u_0,u_1,u_2,u_p) = TrialFunctions(W)
        (v_0,v_1,v_2,v_q) = TestFunctions(W)
        a1 = u_0.dx(0)*v_1[0]*dx + u_0.dx(1)*v_1[1]*dx + (u_1[1].dx(0) - u_1[0].dx(1))*v_2*dx
        a2 = v_0.dx(0)*u_1[0]*dx + v_0.dx(1)*u_1[1]*dx + (v_1[1].dx(0) - v_1[0].dx(1))*u_2*dx
        ah = u_p*v_2*dx + u_2*v_q*dx
        a = a1 + a2 + ah
        L = Constant(0.)*v_q*dx
        return (a,L)



from petsc4py import PETSc
from slepc4py import SLEPc
class SVD_null_space_solver:
    def __init__(self,mat,Tunning={},expected_harmonics=2,printvp=False,customthreshold=1e-15):
        self.vr = PETSc.Vec().create()
        self.vr.setSizes(mat.size[0])
        self.vr.setFromOptions()
        self.vl = PETSc.Vec().create()
        self.vl.setSizes(mat.size[0])
        self.vl.setFromOptions()
        
        self.S = SLEPc.SVD(); self.S.create()
        self.S.setOperator(mat)
        self.S.setWhichSingularTriplets(SLEPc.SVD.Which.SMALLEST)
        if ("max_auto_ncv" in Tunning):
            max_auto_ncv = Tunning["max_auto_ncv"]
        else:
            max_auto_ncv = 200
        
        if ("ncv" in Tunning) and (Tunning["ncv"] > 0) and ("mpd" in Tunning) and (Tunning["mpd"] > 0):
            print("Using custom value : {} {}".format(Tunning["ncv"],Tunning["mpd"]))
            self.S.setDimensions(expected_harmonics,Tunning["ncv"],Tunning["mpd"])
            try:
                self.S.solve()
            except Exception as e:
                print("Exeption encountered while solving :" + str(e) + " \n Giving up (auto increase does not apply with user supplied parameter ncv and mpd")
                raise
            self.numberconverged = self.S.getConverged()
        else:
            nsv = expected_harmonics
            ncv = max(16,nsv*2)
            #mpd =
            self.S.setDimensions(nsv,ncv,ncv)
            try:
                self.S.solve()
            except Exception as e:
                self.numberconverged = 0
                print("Exeption encountered while solving :" + str(e) + " \n Trying with higher ncv and mpd")
            else:
                self.numberconverged = self.S.getConverged()
            # will raise an error when ncv get too big
            while((self.numberconverged < expected_harmonics) and (ncv < max_auto_ncv)):
                ncv += 10
                self.S.setDimensions(nsv,ncv,ncv)
                try:
                    self.S.solve()
                except Exception as e:
                    self.numberconverged = 0
                    print("Exeption encountered while solving :" + str(e) + " \n Trying with higher ncv and mpd")
                    if (ncv >= max_auto_ncv):
                        raise RuntimeError('ncv reached max_auto_ncv without finding enough harmonics and the last try raised an error in the solver. Giving up as it would be left in an unstable state')
                else:
                    self.numberconverged = self.S.getConverged()
        self.n = 0
        for i in range(self.numberconverged):
            if (printvp):
                print(self.S.getSingularTriplet(i))
            if (self.S.getSingularTriplet(i) < customthreshold):
                self.n += 1
    def Get_Dim(self):
        return self.n
    def Get_Vector(self,i):
        self.S.getSingularTriplet(i,self.vl,self.vr)
        return self.vr.getArray()

# Not tested wet
from scipy.sparse import csr_matrix
from sparseqr import qr
class SuiteSparseQR_solver:
    def __init__(self,mat,Tunning={},expected_harmonics=2,printvp=False,customthreshold=1e-15):
        csr = csr_matrix(mat.getValuesCSR()[::-1], shape=mat.size)
        # mat = csr.transpose().tocoo() # optionnal, doc of sparseqr specify that coo is the optimal input format
        Q, R, E, rank = qr( csr.transpose())
        max_rank = max(expected_harmonics,rank) + 1
        self.n = 0
        for i in range(1,max_rank):
            if(printvp):
                print(R[-i])
            if(R[-i] < customthreshold):
                self.n += 1
        if(printvp):
            print("Next value would be : {}\n".format(R[-max_rank]))
        self.N = Q.tocsc()[:,rank:]
    def Get_Dim(self):
        return self.n
    def Get_Vector(self,i):
        return N[:,i].todense()

# Tested in 3D, should not be different here
from scipy.sparse.linalg import eigs
class Scipy_eigs_solver:
    def __init__(self,mat,Tunning={},expected_harmonics=2,printvp=False,customthreshold=1e-15):
        csr = csr_matrix(mat.getValuesCSR()[::-1], shape=mat.size)
        sigma=-1e-1
        if ("eigs_tol" in Tunning):
            tol = Tunning["eigs_tol"]
        else:
            tol = 1e-6
        eigenvalues,eigenvectors = eigs(csr.transpose().dot(csr),k=expected_harmonics,
                                        sigma=sigma,which='LM',tol=tol,return_eigenvectors=True)
        # result is complex by default
        self.eigenvalues = np.real(eigenvalues)
        self.eigenvectors = np.real(eigenvectors)
        
        max_rank = max(expected_harmonics,len(self.eigenvalues))
        self.n = 0
        for i in range(max_rank):
            if(printvp):
                print(self.eigenvalues[i])
            if(self.eigenvalues[i] < customthreshold):
                self.n += 1
    def Get_Dim(self):
        return self.n
    def Get_Vector(self,i):
        return self.eigenvectors[:,i]

def get_harmonic1_basis(mesh,Lu1,DBC=False,Elemdict=None,Tunning={},expected_harmonics=2,printvp=False,customthreshold=1e-15):
    if Elemdict is not None:
        biot_savart_solver = BiotSavart_base(DBC,Elemdict=Elemdict)
    else:
        biot_savart_solver = BiotSavart_base(DBC)
    A = biot_savart_solver.init(mesh)
    print("system size : ",np.shape(A.array()))
    mat = as_backend_type(A).mat()
    if ("solver" in Tunning) and (Tunning["solver"] == "SLEPc_SVD"):
        Solver = SVD_null_space_solver(mat,Tunning=Tunning,expected_harmonics=expected_harmonics,
                                       printvp=printvp,customthreshold=customthreshold)
    elif ("solver" in Tunning) and (Tunning["solver"] == "SuiteSparse_QR"):
        Solver = SuiteSparseQR_solver(mat,Tunning=Tunning,expected_harmonics=expected_harmonics,
                                       printvp=printvp,customthreshold=customthreshold)
    elif ("solver" in Tunning) and (Tunning["solver"] == "Scipy_eigs"):
        Solver = Scipy_eigs_solver(mat,Tunning=Tunning,expected_harmonics=expected_harmonics,
                                       printvp=printvp,customthreshold=customthreshold)
    else:
        Solver = Scipy_eigs_solver(mat,Tunning=Tunning,expected_harmonics=expected_harmonics,
                                       printvp=printvp,customthreshold=customthreshold)
    
    n = Solver.Get_Dim()
    print("Found ",n," element in the basis")
    if (n != expected_harmonics):
        print("Warning : found {} harmonics while {} were expected.".format(n,expected_harmonics))
        print("The number of expected harmonics default to 2, ignore this if less were expected")
        print("Else this might be a threshold to high, this can be set with 'customthreshold' and analysed by setting 'printvp' to 'True'")
        print("If this does not work then the search failed, some options might be passed with 'Tunning'")
    
    # check Bug assign for why an assigner is necessary
    assigner = FunctionAssigner(biot_savart_solver.F1,biot_savart_solver.W.sub(1))
    uharmfull = Function(biot_savart_solver.W)
    uharmFP1 = Function(biot_savart_solver.F1)
    for i in range(n):
        Lu1.append(Function(biot_savart_solver.F1))
        uharmfull.vector().set_local(Solver.Get_Vector(i))
        # uharmFP1.assign((uharmfull.split(True))[1]) # split(True) necessary? # check bug
        assigner.assign(uharmFP1,uharmfull.sub(1))
        uharmFP1tmp = uharmFP1
        for j in range(i):
            uharmFP1.assign(uharmFP1 - assemble(inner(uharmFP1tmp,Lu1[j])*dx)*Lu1[j])
        uharmFP1.assign(uharmFP1/norm(uharmFP1))
        Lu1[i].assign(uharmFP1)
    return n


# TODO : optimize (use restricted space and svd might be overkill)
import scipy
from scipy import linalg, matrix
def get_harmonic1_basis_legacy(mesh,Lu1,DBC=False,printvp=False,customthreshold=1e-15):
    biot_savart_solver = BiotSavart_base(DBC)
    A = biot_savart_solver.init(mesh)
    print("system size : ",np.shape(A.array()))
    print("Symmetric matrix :",np.allclose(A.array(),A.array().T)) # Test as fenics seem to take trialfunction
    u, s, vh = scipy.linalg.svd(A.array()) # on the right et test on the left (a(v,u) and not a(u,v))
    if (printvp):
        print(s)
    null_mask = (s <= customthreshold)
    null_space = scipy.compress(null_mask, vh, axis=0)
    n,l = np.shape(null_space)
    print("Found ",n," element in the basis")
    # check Bug assign for why an assigner is necessary
    assigner = FunctionAssigner(biot_savart_solver.F1,biot_savart_solver.W.sub(1))
    uharmfull = Function(biot_savart_solver.W)
    uharmFP1 = Function(biot_savart_solver.F1)
    for i in range(n):
        Lu1.append(Function(biot_savart_solver.F1))
        uharmfull.vector().set_local(null_space[i])
        # uharmFP1.assign((uharmfull.split(True))[1]) # split(True) necessary? # check bug
        assigner.assign(uharmFP1,uharmfull.sub(1))
        uharmFP1tmp = uharmFP1
        for j in range(i):
            uharmFP1.assign(uharmFP1 - assemble(inner(uharmFP1tmp,Lu1[j])*dx)*Lu1[j])
        uharmFP1.assign(uharmFP1/norm(uharmFP1))
        Lu1[i].assign(uharmFP1)
    return n
    
def boundary_whole(x, on_boundary):
    return on_boundary
