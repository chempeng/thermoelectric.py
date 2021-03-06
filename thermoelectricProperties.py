import numpy as np
from numpy.linalg import norm
from os.path import expanduser
from scipy.interpolate import InterpolatedUnivariateSpline
from scipy.interpolate import PchipInterpolator
from scipy.special import jv
import matplotlib as mpl
from matplotlib import cm
from numpy.matlib import repmat
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
import matplotlib.ticker
from matplotlib.ticker import FormatStrFormatter
from matplotlib.ticker import ScalarFormatter
from mpl_toolkits import mplot3d
from matplotlib.colors import LightSource
import seaborn as sns
from accum import accum
from numpy.linalg import norm


class thermoelectricProperties:

    hBar = 6.582119e-16     # Reduced Planck constant in eV.s
    kB = 8.617330350e-5     # Boltzmann constant in eV/K
    e2C = 1.6021765e-19     # e to Coulomb unit change
    e0 = 8.854187817e-12    # Permittivity in vacuum F/m
    Ang2meter = 1e-10       # Unit conversion from Angestrom to meter
    me = 9.109e-31

    def __init__(self, latticeParameter, dopantElectricCharge, electronEffectiveMass, dielectric, numKpoints, numBands=None, numQpoints=None, electronDispersian=None, kpoints=None, energyMin=0, energyMax=2, numEnergySampling=1000):

        self.latticeParameter = latticeParameter            # Lattice parameter in A
        self.dopantElectricCharge = dopantElectricCharge
        self.electronEffectiveMass = electronEffectiveMass
        self.energyMax = energyMax                          # Maximum energy in eV
        self.energyMin = energyMin                          # Minimum energy in eV
        self.dielectric = dielectric                                        # Relative permittivity
        self.numEnergySampling = numEnergySampling          # Number of energy space samples to generate in eV
        self.numKpoints = numKpoints
        self.numBands = numBands
        self.electronDispersian = electronDispersian
        self.numQpoints = numQpoints

    def energyRange(self):                                  # Create an array of energy space sampling
        energyRange = np.linspace(self.energyMin, self.energyMax, self.numEnergySampling)
        return np.expand_dims(energyRange, axis=0)

    def kpoints(self, path2kpoints, delimiter=None, skiprows=0):
        kpoints = np.loadtxt(expanduser(path2kpoints), delimiter=None, skiprows=0)
        return kpoints

    def temp(self, TempMin=300, TempMax=1301, dT=100):
        temperature = np.arange(TempMin, TempMax, dT)
        return np.expand_dims(temperature, axis=0)

    def bandGap(self, Eg_o, Ao, Bo, Temp=None):
        if Temp is None:
            T = self.temp()
        else:
            T = Temp
        Eg = Eg_o - Ao * np.divide(T**2, T + Bo)
        return Eg

    def analyticalDoS(self, energyRange, alpha):
        DoS_nonparabolic = 1/np.pi**2*np.sqrt(2*energyRange*(1+energyRange*np.transpose(alpha)))*np.sqrt(self.electronEffectiveMass/thermoelectricProperties.hBar**2)**3*(1+(2*energyRange*np.transpose(alpha)))/thermoelectricProperties.e2C**(3./2)
        DoS_parabolic = np.sqrt(energyRange)/np.pi**2*np.sqrt(2)/thermoelectricProperties.hBar**3*self.electronEffectiveMass**(3/2)/thermoelectricProperties.e2C**(3/2)
        DoS = [DoS_nonparabolic,DoS_parabolic]
        return DoS

    def carrierConcentration(self, path2extrinsicCarrierConcentration, bandGap, Ao=None, Bo=None, Nc=None, Nv=None, Temp=None):
        if Temp is None:
            T = self.temp()
        else:
            T = Temp
        if Ao is None and Nc is None:
            raise Exception("Either Ao or Nc should be defined")
        if Bo is None and Nv is None:
            raise Exception("Either Bo or Nv should be defined")
        if Nc is None:
            Nc = Ao * Temp**(3. / 2)
        if Nv is None:
            Nv = Bo * Temp**(3. / 2)
        exCarrierFile = np.loadtxt(expanduser(path2extrinsicCarrierConcentration), delimiter=None, skiprows=0)
        extrinsicCarrierConcentration_tmp = InterpolatedUnivariateSpline(exCarrierFile[0, :], exCarrierFile[1, :] * 1e6)
        extrinsicCarrierConcentration = extrinsicCarrierConcentration_tmp(T)
        intrinsicCarrierConcentration = np.multiply(np.sqrt(np.multiply(Nc, Nv)), np.exp(-(np.divide(bandGap, (2 * thermoelectricProperties.kB * T)))))
        totalCarrierConcentration = intrinsicCarrierConcentration + abs(extrinsicCarrierConcentration)
        return totalCarrierConcentration

    def fermiLevel(self, carrierConcentration, energyRange, DoS, Nc=None, Ao=None, Temp=None):
        if Temp is None:
            T = self.temp()
        else:
            T = Temp
        if Ao is None and Nc is None:
            raise Exception("Either Ao or Nc should be defined")
        if Nc is None:
            Nc = Ao * Temp**(3. / 2)
        JD_CC = np.log(np.divide(carrierConcentration, Nc)) + 1 / np.sqrt(8) * np.divide(carrierConcentration, Nc) - (3. / 16 - np.sqrt(3) / 9) * np.power(np.divide(carrierConcentration, Nc), 2)
        fermiLevelEnergy = thermoelectricProperties.kB * np.multiply(T, JD_CC)
        f, _ = self.fermiDistribution(energyRange=energyRange, fermiLevel=fermiLevelEnergy, Temp=T)
        n = np.trapz(np.multiply(DoS, f), energyRange, axis=1)
        return [fermiLevelEnergy,np.expand_dims(n,axis=0)]

    def fermiDistribution(self, energyRange, fermiLevel, Temp=None):
        if Temp is None:
            T = self.temp()
        else:
            T = Temp

        xi = np.exp((energyRange-fermiLevel.T)/T.T/thermoelectricProperties.kB)
        fermiDirac = 1/(xi+1)
        dfdE = -1*xi/(1+xi)**2/T.T/thermoelectricProperties.kB
        fermi = np.array([fermiDirac, dfdE])
        return fermi

    def electronBandStructure(self, path2eigenval, skipLines):
        with open(expanduser(path2eigenval)) as eigenvalFile:
            for _ in range(skipLines):
                next(eigenvalFile)
            block = [[float(_) for _ in line.split()] for line in eigenvalFile]
        eigenvalFile.close()
        electronDispersian = [range(1, self.numBands + 1)]  # First line is atoms id
        kpoints = np.asarray(block[1::self.numBands + 2])[:, 0:3]
        for _ in range(self.numKpoints):
            binary2Darray = []
            for __ in range(self.numBands):
                binary2Darray = np.append(binary2Darray, block[__ + 2 + (self.numBands + 2) * _][1])
            electronDispersian = np.vstack([electronDispersian, binary2Darray])
        dispersian = [kpoints, electronDispersian]
        return dispersian

    def electronDoS(self, path2DoS, headerLines, numDoSpoints, unitcell_volume, valleyPoint, energyRange):
        DoS = np.loadtxt(expanduser(path2DoS), delimiter=None, skiprows=headerLines, max_rows=numDoSpoints)
        valleyPointEnergy = DoS[valleyPoint, 0]
        DoSSpline = InterpolatedUnivariateSpline(DoS[valleyPoint:, 0] - valleyPointEnergy, DoS[valleyPoint:, 1] / unitcell_volume)
        DoSFunctionEnergy = DoSSpline(energyRange)  # Density of state
        return DoSFunctionEnergy

    def fermiLevelSelfConsistent(self, carrierConcentration, Temp, energyRange, DoS, fermilevel):
        fermi = np.linspace(fermilevel[0]-0.2, fermilevel[0]+0.2, 4000, endpoint=True).T
        result_array = np.empty((np.shape(Temp)[1], np.shape(fermi)[1]))
        idx_j = 0
        for j in Temp[0]:
            idx_i = 0
            for i in fermi[idx_j]:
                f, _ = self.fermiDistribution(energyRange=energyRange, fermiLevel=np.expand_dims(np.array([i]), axis=0), Temp=np.expand_dims(np.array([j]), axis=0))
                tmp = np.trapz(np.multiply(DoS, f), energyRange, axis=1)
                result_array[idx_j, idx_i] = tmp
                idx_i += 1
            idx_j += 1
        diff = np.tile(np.transpose(carrierConcentration), (1, np.shape(fermi)[1])) - abs(result_array)
        min_idx = np.argmin(np.abs(diff), axis=1)
        print("Fermi Level Self Consistent Index ",min_idx)
        Ef = np.empty((1, np.shape(Temp)[1]))
        for Ef_idx in np.arange(len(min_idx)):
            Ef[0,Ef_idx] = fermi[Ef_idx,min_idx[Ef_idx]]
        elm = 0
        n = np.empty((1, np.shape(Temp)[1]))
        for idx in min_idx:
            n[0,elm] = result_array[elm, idx]
            elm += 1
        return [Ef,n]

    def electronGroupVelocity(self, kp, energy_kp, energyRange):
        dE = np.roll(energy_kp, -1, axis=0) - np.roll(energy_kp, 1, axis=0)
        dk = np.roll(kp, -1, axis=0) - np.roll(kp, 1, axis=0)
        dEdk = np.divide(dE, dk)
        dEdk[0] = (energy_kp[1] - energy_kp[0]) / (kp[1] - kp[0])
        dEdk[-1] = (energy_kp[-1] - energy_kp[-2]) / (kp[-1] - kp[-2])
        dEdkSpline = InterpolatedUnivariateSpline(energy_kp, np.array(dEdk))
        dEdkFunctionEnergy = dEdkSpline(energyRange)
        groupVel = dEdkFunctionEnergy / thermoelectricProperties.hBar
        return groupVel

    def analyticalGroupVelocity(self,energyRange, nk, m, valley, dk_len, alpha, temperature):

        meff = np.array(m)*(1+5*alpha.T*thermoelectricProperties.kB*temperature.T)
        ko = 2 * np.pi / self.latticeParameter * np.array(valley)
        del_k = 2*np.pi/self.latticeParameter * dk_len * np.array([1, 1, 1])
        kx = np.linspace(ko[0], ko[0] + del_k[0], nk[0], endpoint=True)  # kpoints mesh
        ky = np.linspace(ko[1], ko[1] + del_k[1], nk[1], endpoint=True)  # kpoints mesh
        kz = np.linspace(ko[2], ko[2] + del_k[2], nk[2], endpoint=True)  # kpoints mesh
        [xk, yk, zk] = np.meshgrid(kx, ky, kz)
        xk_ = np.reshape(xk, -1)
        yk_ = np.reshape(yk, -1)
        zk_ = np.reshape(zk, -1)
        kpoint = np.array([xk_, yk_, zk_])
        mag_kpoint = norm(kpoint, axis=0)
        vel = np.empty([0,len(mag_kpoint)])
        E = np.empty([0,len(mag_kpoint)])
        for i in np.arange(len(temperature[0])):
            _E = thermoelectricProperties.hBar**2 / 2 * ((kpoint[0] - ko[0])**2 / meff[i,0] + (kpoint[1] - ko[1])**2 / meff[i,1] + (kpoint[2] - ko[2]) ** 2 / meff[i,2]) * thermoelectricProperties.e2C
            __vel = thermoelectricProperties.hBar*np.array([kpoint[0]-ko[0], kpoint[1]-ko[1], kpoint[2]-ko[2]])/np.array([meff[i]]).T/(1+2*alpha[0,i]*_E)*thermoelectricProperties.e2C
            _vel = norm(__vel, axis=0)
            E = np.append(E,np.array([_E]), axis=0)
            vel = np.append(vel,np.array([_vel]), axis=0)
            del _E, __vel, _vel
        vg = list([])
        for i in np.arange(len(temperature[0])):
            Ec, indices, return_indices = np.unique(E[i], return_index=True, return_inverse=True)
            vel_g = accum(return_indices, vel[i], func=np.mean, dtype=float)
            ESpline = PchipInterpolator(Ec, vel_g)
            velFunctionEnergy = ESpline(energyRange)[0]
            vg.append(velFunctionEnergy)
            del velFunctionEnergy, ESpline, vel_g, Ec, indices, return_indices
        return np.asarray(vg)

    def matthiessen(self, *args):
        tau = 1. / sum([1. / arg for arg in args])
        tau[np.isinf(tau)] = 0
        return tau

    def tau_p(self, energyRange, alpha, Dv, DA, T, vs, D, rho):

        nonparabolic_term = (1-((alpha.T*energyRange)/(1+2*alpha.T*energyRange)*(1-Dv/DA)))**2-8/3*(alpha.T*energyRange)*(1+alpha.T*energyRange)/(1+2*alpha.T*energyRange)**2*(Dv/DA)
        tau = rho*vs**2*thermoelectricProperties.hBar/np.pi/thermoelectricProperties.kB/T.T/DA/DA*1e9/thermoelectricProperties.e2C/D
        tau_p = tau/nonparabolic_term
        return [tau,tau_p]

    def tau_Screened_Coulomb(self,energyRange, m_c, LD, N):

        g = 8*m_c.T*LD.T**2*energyRange/thermoelectricProperties.hBar**2/thermoelectricProperties.e2C
        var_tmp = np.log(1+g)-g/(1+g)
        tau = 16*np.pi*np.sqrt(2*m_c.T)*(4*np.pi*self.dielectric*thermoelectricProperties.e0)**2/N.T/var_tmp*energyRange**(3/2)/thermoelectricProperties.e2C**(5/2)
        where_are_NaNs = np.isnan(tau)
        tau[where_are_NaNs] = 0
        return tau

    def tau_Unscreened_Coulomb(self,energyRange, m_c, N):

        g = 4*np.pi*(4*np.pi*self.dielectric*thermoelectricProperties.e0)*energyRange/N.T**(1/3)/thermoelectricProperties.e2C
        var_tmp = np.log(1+g**2)
        tau = 16*np.pi*np.sqrt(2*m_c.T)*(4*np.pi*self.dielectric*thermoelectricProperties.e0)**2/N.T/var_tmp*energyRange**(3/2)/thermoelectricProperties.e2C**(5/2)
        where_are_NaNs = np.isnan(tau)
        tau[where_are_NaNs] = 0
        return tau

    def tau_Strongly_Screened_Coulomb(self, D, LD, N):
        tau = thermoelectricProperties.hBar/N.T/np.pi/D/(LD.T**2/(4*np.pi*self.dielectric*thermoelectricProperties.e0))**2*1/thermoelectricProperties.e2C**2
        return tau

    def tau2D_cylinder(self,energyRange, nk, Uo, m, vfrac, valley, dk_len, ro, n=2000):

        meff = np.array(m) * thermoelectricProperties.me
        ko = 2 * np.pi / self.latticeParameter * np.array(valley)
        del_k = 2*np.pi/self.latticeParameter * dk_len * np.array([1, 1, 1])
        N = vfrac/np.pi/ro**2
        kx = np.linspace(ko[0], ko[0] + del_k[0], nk[0], endpoint=True)  # kpoints mesh
        ky = np.linspace(ko[1], ko[1] + del_k[1], nk[1], endpoint=True)  # kpoints mesh
        kz = np.linspace(ko[2], ko[2] + del_k[2], nk[2], endpoint=True)  # kpoints mesh
        [xk, yk, zk] = np.meshgrid(kx, ky, kz)
        xk_ = np.reshape(xk, -1)
        yk_ = np.reshape(yk, -1)
        zk_ = np.reshape(zk, -1)
        kpoint = np.array([xk_, yk_, zk_])
        mag_kpoint = norm(kpoint, axis=0)
        E = thermoelectricProperties.hBar**2 / 2 * ((kpoint[0, :] - ko[0])**2 / meff[0] + (kpoint[1, :] - ko[1])**2 / meff[1] + (kpoint[2, :] - ko[2]) ** 2 / meff[2]) * thermoelectricProperties.e2C
        t = np.linspace(0, 2*np.pi, n)
        a = np.expand_dims(np.sqrt(2 * meff[1] / thermoelectricProperties.hBar**2 * E / thermoelectricProperties.e2C), axis=0)
        b = np.expand_dims(np.sqrt(2 * meff[2] / thermoelectricProperties.hBar**2 * E / thermoelectricProperties.e2C), axis=0)
        ds = np.sqrt((a.T * np.sin(t))**2 + (b.T * np.cos(t))**2)
        cos_theta = ((a * kpoint[0]).T * np.cos(t) + (b * kpoint[1]).T * np.sin(t) + np.expand_dims(kpoint[2]**2, axis=1)) / np.sqrt(a.T**2 * np.cos(t)**2 + b.T**2 * np.sin(t)**2 + np.expand_dims(kpoint[2]**2, axis=1)) / np.expand_dims(mag_kpoint, axis=1)
        delE = thermoelectricProperties.hBar**2 * np.abs((a.T * np.cos(t) - ko[0]) / meff[0] + (b.T * np.sin(t) - ko[1]) / meff[1] + (np.expand_dims(kpoint[2]**2, axis=1) - ko[2] / meff[2]))
        qx = np.expand_dims(kpoint[0], axis=1) - a.T * np.cos(t)
        qy = np.expand_dims(kpoint[1], axis=1) - b.T * np.sin(t)
        qr = np.sqrt(qx**2 + qy**2)
        tau = np.empty((len(ro), len(E)))
        for r_idx in np.arange(len(ro)):
            J = jv(1, ro[r_idx] * qr)
            SR = 2 * np.pi / thermoelectricProperties.hBar * Uo**2 * (2 * np.pi)**3 * (ro[r_idx] * J / qr)**2
            f = SR * (1 - cos_theta) / delE * ds
            int_ = np.trapz(f, t, axis=1)
            tau[r_idx] = 1 / (N[r_idx] / (2 * np.pi)**3 * int_) * thermoelectricProperties.e2C
        Ec, indices, return_indices = np.unique(E, return_index=True, return_inverse=True)
        tau_c = np.empty((len(ro), len(indices)))
        tauFunctionEnergy = np.empty((len(ro), len(energyRange[0])))
        for r_idx in np.arange(len(ro)):
            tau_c[r_idx] = accum(return_indices, tau[r_idx], func=np.mean, dtype=float)
        for tau_idx in np.arange(len(tau_c)):
            ESpline = PchipInterpolator(Ec[30:], tau_c[tau_idx,30:])
            tauFunctionEnergy[tau_idx] = ESpline(energyRange)
        return tauFunctionEnergy

    def tau3D_spherical(self,energyRange, nk, Uo, m, vfrac, valley, dk_len, ro, n=32):
        meff = np.array(m) * thermoelectricProperties.me
        ko = 2 * np.pi / self.latticeParameter * np.array(valley)
        del_k = 2*np.pi/self.latticeParameter * dk_len * np.array([1, 1, 1])
        N = 3*vfrac/4/np.pi/ro**3
        kx = np.linspace(ko[0], ko[0] + del_k[0], nk[0], endpoint=True)  # kpoints mesh
        ky = np.linspace(ko[1], ko[1] + del_k[1], nk[1], endpoint=True)  # kpoints mesh
        kz = np.linspace(ko[2], ko[2] + del_k[2], nk[2], endpoint=True)  # kpoints mesh
        [xk, yk, zk] = np.meshgrid(kx, ky, kz)
        xk_ = np.reshape(xk, -1)
        yk_ = np.reshape(yk, -1)
        zk_ = np.reshape(zk, -1)
        kpoint = np.array([xk_, yk_, zk_])
        mag_kpoint = norm(kpoint, axis=0)
        E = thermoelectricProperties.hBar**2 / 2 * ((kpoint[0, :] - ko[0])**2 / meff[0] + (kpoint[1, :] - ko[1])**2 / meff[1] + (kpoint[2, :] - ko[2]) ** 2 / meff[2]) * thermoelectricProperties.e2C
        scattering_rate = np.zeros((len(ro), len(E)))
        nu = np.linspace(0, np.pi, n)
        z_ = -1 * np.cos(nu)
        r = np.sqrt(1.0 - z_**2)[:, None]
        theta = np.linspace(0, 2 * np.pi, n)[None, :]
        x_ = r * np.cos(theta)
        y_ = r * np.sin(theta)
        for u in np.arange(len(E)):

            Q = np.zeros((2 * (n-2) * (n - 1), 3))
            A = np.zeros((2 * (n-2) * (n - 1), 1))
            k = 0
            a_axis = np.sqrt(2 / (thermoelectricProperties.hBar**2 * thermoelectricProperties.e2C) * meff[0] * E[u])
            b_axis = np.sqrt(2 / (thermoelectricProperties.hBar**2 * thermoelectricProperties.e2C) * meff[1] * E[u])
            c_axis = np.sqrt(2 / (thermoelectricProperties.hBar**2 * thermoelectricProperties.e2C) * meff[2] * E[u])

            y = -1 * b_axis * y_ + ko[1]
            x = -1 * a_axis * x_ + ko[0]
            Z_ = c_axis * z_ + ko[2]
            z = np.tile(Z_[:, None], (1,n))
            for j in np.arange(1,n-1):
                for i in np.arange(2,n):
                    S = np.array(np.array([x[i,j],y[i,j],z[i,j]])+np.array([x[i-1,j],y[i-1,j],z[i-1,j]])+np.array([x[i-1,j-1],y[i-1,j-1],z[i-1,j-1]]))
                    Q[k] = S/3
                    a = norm(np.array([x[i,j],y[i,j],z[i,j]])-np.array([x[i-1,j],y[i-1,j],z[i-1,j]]))
                    b = norm(np.array([x[i-1,j],y[i-1,j],z[i-1,j]])-np.array([x[i-1,j-1],y[i-1,j-1],z[i-1,j-1]]))
                    c = norm(np.array([x[i-1,j-1],y[i-1,j-1],z[i-1,j-1]])-np.array([x[i,j],y[i,j],z[i,j]]))
                    s = a+b+c
                    s = s/2
                    A[k] = np.sqrt(s*(s-a)*(s-b)*(s-c))
                    k += 1
            for j in np.arange(1,n-1):
                for i in np.arange(1,n-1):
                    S = np.array([x[i,j-1],y[i,j-1],z[i,j-1]])+np.array([x[i,j],y[i,j],z[i,j]])+np.array([x[i-1,j-1],y[i-1,j-1],z[i-1,j-1]])
                    Q[k] = S/3
                    a = norm(np.array([x[i,j-1],y[i,j-1],z[i,j-1]])-np.array([x[i,j],y[i,j],z[i,j]]))
                    b = norm(np.array([x[i,j],y[i,j],z[i,j]])-np.array([x[i-1,j-1],y[i-1,j-1],z[i-1,j-1]]))
                    c = norm(np.array([x[i-1,j-1],y[i-1,j-1],z[i-1,j-1]])-np.array([x[i,j-1],y[i,j-1],z[i,j-1]]))
                    s = a+b+c
                    s = s/2
                    A[k] = np.sqrt(s*(s-a)*(s-b)*(s-c))
                    k += 1
            for i in np.arange(2,n):
                S = np.array([x[i,0],y[i,0],z[i,0]])+np.array([x[i-1,0],y[i-1,0],z[i-1,0]])+np.array([x[i-1,-2],y[i-1,-2],z[i-1,-2]])
                Q[k] = S/3
                a = norm(np.array([x[i,0],y[i,0],z[i,0]])-np.array([x[i-1,0],y[i-1,0],z[i-1,0]]))
                b = norm(np.array([x[i-1,0],y[i-1,0],z[i-1,0]])-np.array([x[i-1,-2],y[i-1,-2],z[i-1,-2]]))
                c = norm(np.array([x[i-1,-2],y[i-1,-2],z[i-1,-2]])-np.array([x[i,0],y[i,0],z[i,0]]))
                s = a+b+c
                s = s/2
                A[k] = np.sqrt(s*(s-a)*(s-b)*(s-c))
                k += 1
            for i in np.arange(1,n-1):
                S = np.array([x[i,-2],y[i,-2],z[i,-2]])+np.array([x[i,0],y[i,0],z[i,0]])+np.array([x[i-1,-2],y[i-1,-2],z[i-1,-2]])
                Q[k] = S/3
                a = norm(np.array([x[i,-2],y[i,-2],z[i,-2]])-np.array([x[i,0],y[i,0],z[i,0]]))
                b = norm(np.array([x[i,0],y[i,0],z[i,0]])-np.array([x[i-1,-2],y[i-1,-2],z[i-1,-2]]))
                c = norm(np.array([x[i-1,-2],y[i-1,-2],z[i-1,-2]])-np.array([x[i,-2],y[i,-2],z[i,-2]]))
                s = a+b+c
                s = s/2
                A[k] = np.sqrt(s*(s-a)*(s-b)*(s-c))
                k += 1
            qx = kpoint[0,u] - Q[:,0]
            qy = kpoint[1,u] - Q[:,1]
            qz = kpoint[2,u] - Q[:,2]
            q  = np.sqrt(qx**2+qy**2+qz**2)
            cosTheta = np.matmul(kpoint[:,u][None,:],Q.T)/norm(kpoint[:,u])/np.sqrt(np.sum(Q**2,axis=1))
            delE = np.abs(thermoelectricProperties.hBar**2*((Q[:,0]-ko[0])/meff[0]+(Q[:,1]-ko[1])/meff[1]+(Q[:,2]-ko[2])/meff[2]))
            for ro_idx in  np.arange(len(ro)):
              M = 4*np.pi*Uo*(1/q*np.sin(ro[ro_idx]*q)-ro[ro_idx]*np.cos(ro[ro_idx]*q))/(q**2)
              SR = 2*np.pi/thermoelectricProperties.hBar*M*np.conj(M)
              f = SR/delE*(1-cosTheta);
              scattering_rate[ro_idx,u] = N[ro_idx]/(2*np.pi)**3*np.sum(f*A.T)
        return scattering_rate


    def electricalProperties(self, E, DoS, vg, Ef, dfdE, Temp, tau):
        X = DoS * vg**2 * dfdE
        Y = (E - np.transpose(Ef)) * X
        Z = (E - np.transpose(Ef)) * Y
        Sigma = -1 * np.trapz(X * tau, E, axis=1) / 3 * thermoelectricProperties.e2C
        S = -1*np.trapz(Y * tau, E, axis=1)/np.trapz(X * tau, E, axis=1)/Temp
        PF = Sigma*S**2
        ke = -1*(np.trapz(Z * tau, E, axis=1) - np.trapz(Y * tau, E, axis=1)**2/np.trapz(X * tau, E, axis=1))/Temp/3 * thermoelectricProperties.e2C
        delta_0 = np.trapz(X * tau* E, E, axis=1)
        delta_1 = np.trapz(X * tau* E, E, axis=1)/ np.trapz(X * tau, E, axis=1)
        delta_2 = np.trapz(X * tau* E**2, E, axis=1)/ np.trapz(X * tau, E, axis=1)
        Lorenz = (delta_2-delta_1**2)/Temp/Temp
        coefficients = [Sigma, S[0], PF[0], ke[0], delta_1, delta_2, Lorenz[0]]
        return coefficients

    def filteringEffect(self, U0, tau0, tauOff, energyRange, electronBandStructure, temp, electronDoS, electronGroupVelocity, bandGap, carrierConcentration, fermiLevel, fermiDistribution, factor, q, uIncrement=0.05, tauIncrement=1e-15, tempIndex=0):
        n = 0
        m = 0
        sMatrix = np.array([])
        # rMatrix = np.array([])
        # pfMatrix = np.array([])

        for _ in np.arange(0.1, U0, uIncrement):
            m += 1
            for __ in np.arange(tauIncrement, tau0, tauIncrement):
                tauInc = np.ones(len(Erange))
                tauInc[np.where(Erange < _)] = __
                tau_on = self.matthiessen(energyRange, tauOff, tauInc)
                s, r, c, pf, X, Y = self.electricalProperties(energyRange, electronBandStructure, temp, electronDoS, electronGroupVelocity, tau_on, bandGap, carrierConcentration, fermiLevel, fermiDistribution, factor, q)
                sMatrix = np.append(sMatrix, s[tempIndex])
                n += 1
        sMatrix = np.reshape(sMatrix, (n, m))
        return sMatrix

    # def qpoints(self):
    #     qpoints = np.array([np.zeros(self.numQpoints), np.zeros(self.numQpoints), np.linspace(-math.pi / self.latticeParameter, math.pi / self.latticeParameter, num=self.numQpoints)])
    #     return qpoints

    # def dynamicalMatrix(self, path2massWeightedHessian, path2atomsPositions, skipLines, numAtoms, baseLatticePoint, numAtomsInUnitCell, qpoints):
    #     with open(os.path.expanduser(path2massWeightedHessian)) as hessianFile:
    #         hessianMatrix = hessianFile.readlines()
    #     hessianMatrix = [line.split() for line in hessianMatrix]
    #     hessianMatrix = np.array([[float(_) for _ in __] for __ in hessianMatrix])
    #     hessianFile.close()
    #     hessianSymmetry = (np.triu(hessianMatrix) + np.tril(hessianMatrix).transpose()) / 2
    #     hessianMatrix = hessianSymmetry + np.triu(hessianSymmetry, 1).transpose()
    #     #
    #     with open(os.path.expanduser(path2atomsPositions)) as atomsPositionsFile:
    #         atomsPositions = atomsPositionsFile.readlines()
    #     atomsPositions = [line.split() for line in atomsPositions]
    #     [atomsPositions.pop(0) for _ in range(skipLines)]
    #     atomsPositions = np.array([[float(_) for _ in __] for __ in atomsPositions[0:numAtoms]])
    #     atomsPositions = atomsPositions[atomsPositions[:, 0].argsort()]
    #     # atomsPositions = np.sort(atomsPositions.view('i8,i8,f8,f8,f8,f8,f8,f8'), order=['f0'], axis=0).view(np.float)
    #     latticePoints = np.array([_[2:5] for _ in atomsPositions[::numAtomsInUnitCell]])
    #     latticePointsVectors = latticePoints - numpy.matlib.repmat(latticePoints[baseLatticePoint], len(latticePoints), 1)
    #     dynamicalMatrix = np.zeros((numAtomsInUnitCell * 3, numAtomsInUnitCell * 3))
    #     for _ in range(self.numQpoints):
    #         dynamMatPerQpoint = np.zeros((numAtomsInUnitCell * 3, numAtomsInUnitCell * 3))
    #         for __ in range(len(latticePointsVectors)):
    #             sumMatrix = hessianMatrix[__ * numAtomsInUnitCell * 3: (__ + 1) * numAtomsInUnitCell * 3, baseLatticePoint * numAtomsInUnitCell * 3: (baseLatticePoint + 1) * numAtomsInUnitCell * 3] * cmath.exp(-1j * np.dot(latticePointsVectors[__], qpoints[:, _]))
    #             dynamMatPerQpoint = dynamMatPerQpoint + sumMatrix
    #         dynamicalMatrix = np.append(dynamicalMatrix, dynamMatPerQpoint, axis=0)
    #     dynamicalMatrix = dynamicalMatrix[numAtomsInUnitCell * 3:]
    #     eigVal = np.array([])
    #     eigVec = np.zeros((numAtomsInUnitCell * 3, numAtomsInUnitCell * 3))
    #     for _ in range(self.numQpoints):
    #         dynmat = dynamicalMatrix[_ * numAtomsInUnitCell * 3:(_ + 1) * numAtomsInUnitCell * 3]
    #         eigvals, eigvecs, = np.linalg.eigh(dynmat)
    #         eigVal = np.append(eigVal, eigvals).reshape(-1, numAtomsInUnitCell * 3)
    #         eigVec = np.append(eigVec, eigvecs, axis=0)
    #     eigVec = eigVec[numAtomsInUnitCell * 3:]
    #     frequencies = np.sqrt(np.abs(eigVal.real)) * np.sign(eigVal.real)
    #     # conversion_factor_to_THz = 15.633302
    #     # frequencies = frequencies * conversion_factor_to_THz
    #     return eigVec

    # def phonopyQpointYamlInterface(self, path2QpointYaml):
    #     qpointsData = yaml.load(open("qpoints.yaml"))
    #     nqpoint = qpointsData['nqpoint']
    #     natom = qpointsData['natom']
    #     qpoints = []
    #     qpoints = np.append(qpoints, [qpointsData['phonon'][_]['q-position'] for _ in range(nqpoint)]).reshape(-1, 3)
    #     frequency = []
    #     frequency = np.append(frequency, [[qpointsData['phonon'][_]['band'][__]['frequency'] for __ in range(3 * natom)] for _ in range(nqpoint)]). reshape(-1, 3 * natom)
    #     eigVal = np.array([])
    #     eigVec = np.zeros((natom * 3, natom * 3))
    #     for _ in range(nqpoint):
    #         dynmat = []
    #         dynmat_data = qpointsData['phonon'][_]['dynamical_matrix']
    #         for row in dynmat_data:
    #             vals = np.reshape(row, (-1, 2))
    #             dynmat.append(vals[:, 0] + vals[:, 1] * 1j)
    #         dynmat = np.array(dynmat)
    #         eigvals, eigvecs, = np.linalg.eigh(dynmat)
    #         eigVal = np.append(eigVal, eigvals).reshape(-1, natom * 3)
    #         eigVec = np.append(eigVec, eigvecs, axis=0)
    #     eigVec = eigVec[natom * 3:]
    #     frequencies = np.sqrt(np.abs(eigVal.real)) * np.sign(eigVal.real)
    #     conversion_factor_to_THz = 15.633302
    #     frequencies = frequencies * conversion_factor_to_THz
    #     return eigVec

    # def gaussianDestribution(self, sigma, expectedValue, qpoints):
    #     gauss = (1.0 / np.sqrt(2 * pi) / sigma) * np.exp((-1.0 / 2) * np.power(((qpoints - expectedValue) / sigma), 2))
    #     return gauss

    # def singleWave(self, path2atomsPosition, numberOfAtomsInChain, skipLines)
    # def __str(self):

    # def __repr(self):


# Qpoint = np.array([np.zeros(silicon.numQpoints), np.zeros(silicon.numQpoints), np.linspace(-math.pi / silicon.latticeParameter, math.pi / silicon.latticeParameter, num=silicon.numQpoints)])
# print len(Qpoint[1])
# dynamicalMatrix = thermoelectricProperties.dynamicalMatrix(silicon, '~/Desktop/Notes/Box_120a_Lambda_10a/Si-hessian-mass-weighted-hessian.d', '~/Desktop/Notes/Box_120a_Lambda_10a/data.Si-3x3x3', 15, 216, 14, 8, Qpoint)
# print dynamicalMatrix
# print(dynamicalMatrix)
# Eig = thermoelectricProperties.phonopyQpointYamlInterface(silicon, '~/Desktop/qpoints.yaml')
# np.savetxt('EigVec', Eig.real, fmt='%10.5f', delimiter=' ')
