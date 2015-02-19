"""
This file is part of the Fourier-Hankel Particle-In-Cell code (FB-PIC)

This file defines the structure and methods associated with the fields,
that are used during a PIC cycle.
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.constants import c, mu_0, epsilon_0
from fbpic.hankel_dt import DHT

class Fields(object) :
    """
    Top-level class, which contains :
    - the spatial and spectral grids
    - the Hankel transform objects
    - the method to push the fields in time
    - the methods to transform the fields back and forth
    """

    def __init__( Nz, zmax, Nr, rmax, Nm, dt ) :
        """
        Initialize the components of the Fields object

        Parameters
        ----------
        Nz : int
            The number of gridpoints in z

        zmax : float
            The size of the simulation box along z
            
        Nr : int
            The number of gridpoints in r

        rmax : float
            The size of the simulation box along r

        Nm : int
            The number of azimuthal modes

        dt : float
            The timestep of the simulation, required for the
            coefficients of the psatd scheme
        """

        # Convert Nz to the nearest odd integer
        # (easier for the interpretation of the FFT)
        Nz = 2*int(Nz/2) + 1
        
        # Register the arguments inside the object
        self.Nz = Nz
        self.zmax = zmax
        self.Nr = Nr
        self.rmax = rmax
        self.Nm = Nm
        self.dt = dt

        # Infer the values of the z and kz grid
        dz = zmax/Nz
        z = dz * np.arange( 0, Nz )
        kz = 2*np.pi* np.fft.fftfreq( Nz, dz ) 
        # (According to FFT conventions, the kz array starts with
        # positive frequencies and ends with negative frequency.)
        
        # Create the list of the transformers, which convert the fields
        # back and forth between the spatial and spectral grid
        # (one object per azimuthal mode)
        self.trans = []
        for m in range(Nm) :
            self.trans.append( SpectralTransformer(Nz, Nr, m, rmax) )

        # Create the interpolation grid for each modes
        # (one grid per azimuthal mode)
        self.interp = [ ]
        for m in range(Nm) :
            # Extract the inhomogeneous radial grid for mode m
            r = self.trans[m].dht.get_r()
            # Create the object
            self.interp.append( InterpolationGrid( z, r, m ) )

        # Create the spectral grid for each mode, as well as
        # the psatd coefficients
        # (one grid per azimuthal mode)
        self.spect = [ ]
        self.psatd = [ ]
        for m in range(Nm) :
            # Extract the inhomogeneous spectral grid for mode m
            kr = 2*np.pi * self.trans[m].dht.get_nu()
            # Create the object
            self.spect.append( SpectralGrid( kz, kr, m ) )
            self.psatd.append( PsatdCoeffs( self.spect.kz,
                                            self.spect.kr, m, dt ) )

    def push(self) :
        """
        Push the different azimuthal modes over one timestep,
        in spectral space.
        """
        # Push each azimuthal grid individually, by passing the
        # corresponding psatd coefficients
        for m in range(self.Nm) :
            self.spect[m].push_eb_with( self.psatd[m] )
            self.spect[m].push_rho()

    def correct_currents(self) :
        """
        Correct the currents so that they satisfy the
        charge conservation equation
        """
        # Correct each azimuthal grid individually
        for m in range(self.Nm) :
            self.spect[m].correct_currents( self.dt )

    def interp2spect(self, fieldtype) :
        """
        Transform the fields `fieldtype` from the interpolation grid to the spectral grid
        """

        # Check the validity of fieldtype
        if (fieldtype in ['E', 'B', 'J', 'rho']) == False :
            raise ValueError( 'Invalid string for fieldtype: %s' %fieldtype )
        
class InterpolationGrid(object) :
    """
    Contains the fields and coordinates of the spatial grid.

    Main attributes :
    - z,r : 1darrays containing the positions of the grid
    - Ex, Ey, Ez, Bx, By, Bz, Jx, Jy, Jz, rho :
      2darrays containing the fields.
    """

    def __init__(self, z, r, m ) :
        """
        Allocates the matrices corresponding to the spatial grid
        
        Parameters
        ----------
        z : 1darray of float
            The positions of the longitudinal, spatial grid
        
        r : 1darray of float
            The positions of the radial, spatial grid

        m : int
            The index of the mode
        """

        # Register the arrays and their length
        Nz = len(z)
        Nr = len(r)
        self.Nz = Nz
        self.z = z
        self.Nr = Nr
        self.r = r
        self.m = m

        # Allocate the fields arrays
        self.Ex = np.zeros( (Nz, Nr), dtype='complex' )
        self.Ey = np.zeros( (Nz, Nr), dtype='complex' )
        self.Ez = np.zeros( (Nz, Nr), dtype='complex' )
        self.Bx = np.zeros( (Nz, Nr), dtype='complex' )
        self.By = np.zeros( (Nz, Nr), dtype='complex' )
        self.Bz = np.zeros( (Nz, Nr), dtype='complex' )
        self.Jx = np.zeros( (Nz, Nr), dtype='complex' )
        self.Jy = np.zeros( (Nz, Nr), dtype='complex' )
        self.Jz = np.zeros( (Nz, Nr), dtype='complex' )
        self.rho = np.zeros( (Nz, Nr), dtype='complex' )

    def project_on_grid(self, theta) :
        # Use griddata
        pass

class SpectralGrid(object) :
    """
    Contains the fields and coordinates of the spectral grid.

    Main attributes :
    """

    def __init__(self, kz, kr, m ) :
        """
        Allocates the matrices corresponding to the spectral grid
        
        Parameters
        ----------
        kz : 1darray of float
            The positions of the longitudinal, spectral grid
        
        kr : 1darray of float
            The positions of the radial, spectral grid

        m : int
            The index of the mode
        """
        # Register the arrays and their length
        Nz = len(kz)
        Nr = len(kr)
        self.Nr = Nr
        self.Nz = Nz
        self.m = m
        self.kz, self.kr = np.meshgrid( kz, kr, indexing='ij' )
        
        # Allocate the fields arrays
        self.Ep = np.zeros( (Nz, Nr), dtype='complex' )
        self.Em = np.zeros( (Nz, Nr), dtype='complex' )
        self.Ez = np.zeros( (Nz, Nr), dtype='complex' )
        self.Bp = np.zeros( (Nz, Nr), dtype='complex' )
        self.Bm = np.zeros( (Nz, Nr), dtype='complex' )
        self.Bz = np.zeros( (Nz, Nr), dtype='complex' )
        self.Jp = np.zeros( (Nz, Nr), dtype='complex' )
        self.Jm = np.zeros( (Nz, Nr), dtype='complex' )
        self.Jz = np.zeros( (Nz, Nr), dtype='complex' )
        self.rho_prev = np.zeros( (Nz, Nr), dtype='complex' )
        self.rho_next = np.zeros( (Nz, Nr), dtype='complex' )
        self.F = np.zeros( (Nz, Nr), dtype='complex' )

    def correct_currents(self, dt) :
        """
        Correct the currents so that they satisfies the
        charge conservation equation

        Parameters
        ----------
        dt : float
            Timestep of the simulation
        """

        # Get the corrective field F
        inv_dt = 1./dt
        i = 1.j   # Imaginary number i**2 = -1
        self.F[:,:] = -1./( self.kz**2 + self.kr**2 ) * \
            ( (self.rho_next - self.rho_prev)*inv_dt \
            + i*self.kz*self.Jz + self.kr*( self.Jp - self.Jm ) ) 
            
        # Correct the current accordingly
        self.jp += 0.5*self.kr*self.
        self.jp += -0.5*self.kr*self.F
        self.jp += -i*self.kz*self.F

    def push_eb_with(self, ps ) :
        """
        Pushes the fields over one timestep, using the psatd coefficients.

        Parameters
        ----------
        ps : PsatdCoeffs object
            psatd object corresponding to the same m mode
        """
        # Check that psatd object passed as argument is the right one
        # (i.e. corresponds to the right mode)
        assert( self.m == ps.m )

        # Define the complex number i (i**2 = -1)
        i = 1.j

        # Save the electric fields, since it is needed for the B push
        ps.Ep[:,:] = self.Ep[:,:]
        ps.Em[:,:] = self.Em[:,:]
        ps.Ez[:,:] = self.Ez[:,:]

        # Calculate useful auxiliary matrices
        ps.j_coef[:,:] = mu_0*c**2*ps.inv_w2*( 1 - ps.C )
        ps.rho_diff[:,:] = c**2/epsilon_0*ps.inv_w2*(     \
                    self.rho_next*(    1   - ps.S_wdt) \
                  - self.rho_prev*(  ps.C  - ps.S_wdt) )
    
        # Push the E field
        
        self.Ep[:,:] = ps.C*self.Ep + 0.5*self.kr*ps.rho_diff \
            + ps.S_w*( -i*0.5*self.kr*self.Bz + self.kz*self.Bp - mu_0*self.jp )

        self.Em[:,:] = ps.C*self.Em - 0.5*self.kr*ps.rho_diff \
            + ps.S_w*( -i*0.5*self.kr*self.Bz - self.kz*self.Bm - mu_0*self.jm )

        self.Ez[:,:] = ps.C*self.Ez - i*self.kz*ps.rho_diff \
            + ps.S_z*( i*self.kr*self.Bp + i*self.kr*self.Bm - mu_0*self.jz )

        # Push the B field
        
        self.Bp[:,:] = ps.C*self.Bp \
            - ps.S_w*( -i*0.5*self.kr*ps.Ez + self.kz*ps.Ep ) \
            + ps.j_coef*( -i*0.5*self.kr*self.Jz + self.kz*self.Jp )

        self.Bm[:,:] = ps.C*self.Bm \
            - ps.S_w*( -i*0.5*self.kr*ps.Ez - self.kz*ps.Em ) \
            + ps.j_coef*( -i*0.5*self.kr*self.Jz - self.kz*self.Jm )

        self.Bz[:,:] = ps.C*self.Bz \
            - ps.S_w*( i*self.kr*ps.Ep + i*self.kr*ps.Em ) \
            + ps.j_coef*( i*self.kr*self.Jp + i*self.kr*self.Jm )


    def push_rho(self) :
        """
        Transfer the values of rho_next to rho_prev,
        and set rho_next to zero
        """
        self.rho_prev[:,:] = self.rho_next[:,:]
        self.rho_next[:,:] = 0.
            
    def project_on_grid(self, theta) :
        """
        Project on a regular grid, for plotting purposes, at a given theta
        """
        # Do FFT shift ?
        pass


class PsatdCoeffs(object) :
    """
    Contains the coefficients of the PSATD scheme for a given mode.
    """
    
    def __init__( self, kz, kr, m, dt ) :
        """
        Allocates the coefficients matrices for the psatd scheme.
        
        Parameters
        ----------
        kz : 2darray of float
            The positions of the longitudinal, spectral grid
        
        kr : 2darray of float
            The positions of the radial, spectral grid

        m : int
            Index of the mode
            
        dt : float
            The timestep of the simulation
        """

        # Register m
        self.m = m
    
        # Construct the omega array
        w = c*np.sqrt( kz**2 + kr**2 )

        # Construct the coefficient array
        self.C = np.cos( w*dt )
        self.S_wdt = np.sin( w*dt )/(w*dt)
        self.inv_w2 = 1./w**2

        # Allocate useful auxiliary matrices
        self.rho_diff = np.zeros( (Nz, Nr), dtype='complex' )
        self.j_coef = np.zeros( (Nz, Nr), dtype='complex' )
        self.Ep = np.zeros( (Nz, Nr), dtype='complex' )
        self.Em = np.zeros( (Nz, Nr), dtype='complex' )
        self.Ez = np.zeros( (Nz, Nr), dtype='complex' )
        

class SpectralTransformer(object) :
    """
    Object that allows to transform the fields back and forth between the
    spectral and interpolation grid.

    Attributes :
    - dht : the discrete Hankel transform object that operates along r

    Main methods :
    - spect2interp_scal :
        converts a scalar field from the spectral to the interpolation grid
    - spect2interp_vect :
        converts a vector field from the spectral to the interpolation grid
    - interp2spect_scal :
        converts a scalar field from the interpolation to the spectral grid
    - interp2spect_vect :
        converts a vector field from the interpolation to the spectral grid
    """

    def __init__(self, Nz, Nr, m, rmax ) :
        """
        Initializes the dht attributes, which contain auxiliary
        matrices allowing to transform the fields quickly

        Parameters
        ----------
        Nz, Nr : int
            Number of points along z and r respectively

        m : int
            Index of the mode (needed for the Hankel transform)

        rmax : float
            The size of the simulation box along r.
        """
        # Initialize the DHT (local implementation, see hankel_dt.py)
        print('Preparing the Discrete Hankel Transform for mode %d' %m)
        self.dht = DHT( m, Nr, rmax, 'QDHT' )
        
    def spect2interp_scal( self, spect_array, interp_array ) :
        """
        Convert a scalar field from the spectral grid
        to the interpolation grid.

        Parameters
        ----------
        spect_array : 2darray
           A complex array representing the fields in spectral space, from 
           which to compute the values of the interpolation grid
           The first axis should correspond to z and the second axis to r.

        interp_array : 2darray
           A complex array representing the fields on the interpolation
           which is overwritten by this function.
        """

        # Perform the FFT first (along axis 0, which corresponds to z)
        interp_array = np.fft.ifft( spect_array, axis=0 )

        # Then perform the DHT (along axis -1, which corresponds to r)
        interp_array = self.dht.inverse_transform( interp_array, axis=-1 )

    def spect2interp_vect( self, spect_array_p, spect_array_m,
                          interp_array_x, interp_array_y ) :
      """
        Convert a transverse vector field in the spectral space (e.g. Ep, Em)
        to the interpolation grid (e.g. Ex, Ey)

        Parameters
        ----------
        spect_array_p, spect_array_m : 2darray
           A complex array representing the fields in spectral space, from 
           which to compute the values of the interpolation grid
           The first axis should correspond to z and the second axis to r.

        interp_array_x, interp_array_y : 2darray
           A complex array representing the fields on the interpolation
           which is overwritten by this function.
        """
        
        # Recover spect_array_x, spect_array_y (Cartesian components)
        # from spect_array_p, spect_array_m (combination of Cartesian components
        # that separate in the Maxwell equations)
        spect_array_x = 
        
        

    def interp2spect_scal( self interp_array, spect_array ) :
    
    def interp2spect_vect( self, interp_array, spect_array ) :
        pass

