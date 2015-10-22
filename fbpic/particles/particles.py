"""
This file is part of the Fourier-Bessel Particle-In-Cell code (FB-PIC)
It defines the structure and methods associated with the particles.
"""
import numpy as np
import matplotlib.pyplot as plt
from scipy.constants import c

# Load the standard numpy routines
from numpy_methods import *
# Load the utility methods
from utility_methods import *

# If numba is installed, it can make the code much faster
try :
    from numba_methods import *
    numba_installed = True
except ImportError :
    numba_installed = False

# If numbapro is installed, it potentially allows to use a GPU
try :
    from cuda_methods import *
    from fbpic.cuda_utils import *
    cuda_installed = True
except :
    cuda_installed = False


class Particles(object) :
    """
    Class that contains the particles data of the simulation

    Main attributes
    ---------------
    - x, y, z : 1darrays containing the Cartesian positions
                of the macroparticles (in meters)
    - uz, uy, uz : 1darrays containing the unitless momenta
                (i.e. px/mc, py/mc, pz/mc)
    At the end or start of any PIC cycle, the momenta should be
    one half-timestep *behind* the position.
    """

    def __init__(self, q, m, n, Npz, zmin, zmax,
                    Npr, rmin, rmax, Nptheta, dt,
                    dens_func=None,
                    ux_m=0., uy_m=0., uz_m=0.,
                    ux_th=0., uy_th=0., uz_th=0.,
                    continuous_injection=True,
                    use_numba=True, use_cuda=False,
                    use_cuda_memory=True ) :
        """
        Initialize a uniform set of particles

        Parameters
        ----------
        q : float (in Coulombs)
           Charge of the particle species 

        m : float (in kg)
           Mass of the particle species 

        n : float (in particles per m^3)
           Peak density of particles
           
        Npz : int
           Number of macroparticles along the z axis
           
        zmin, zmax : floats (in meters)
           z positions between which the particles are initialized

        Npr : int
           Number of macroparticles along the r axis

        rmin, rmax : floats (in meters)
           r positions between which the particles are initialized

        Nptheta : int
           Number of macroparticules along theta

        dt : float (in seconds)
           The timestep for the particle pusher

        ux_m, uy_m, uz_m: floats (dimensionless), optional
           Normalized mean momenta of the injected particles in each direction

        ux_th, uy_th, uz_th: floats (dimensionless), optional
           Normalized thermal momenta in each direction
           
        dens_func : callable, optional
           A function of the form :
           def dens_func( z, r ) ...
           where z and r are 1d arrays, and which returns
           a 1d array containing the density *relative to n*
           (i.e. a number between 0 and 1) at the given positions

        continuous_injection : bool, optional
           Whether to continuously inject the particles,
           in the case of a moving window

        use_numba : bool, optional
            Whether to use numba-compiled code on the CPU
           
        use_cuda : bool, optional
            Wether to use the GPU or not. Overrides use_numba.

        use_cuda_memory : bool, optional
            Wether to use manual memory management. Recommended.
        """
        # Register the timestep
        self.dt = dt

        # Define wether or not to use the GPU
        self.use_cuda = use_cuda
        self.use_cuda_memory = use_cuda_memory
        if (self.use_cuda==True) and (cuda_installed==False) :
            print '*** Cuda not available for the particles.'
            print '*** Performing the particle operations on the CPU.'
            self.use_cuda = False
        if self.use_cuda == False:
            self.use_cuda_memory == False
        if self.use_cuda == True:
            print 'Using the GPU for the particles.'

        # Define whether or not to use numba on a CPU
        self.use_numba = use_numba
        if self.use_cuda == True :
            self.use_numba = False
        if (self.use_numba==True) and (numba_installed==False) :
            print 'Numba is not installed ; the code will be slow.'
        
        # Register the properties of the particles
        # (Necessary for the pusher, and when adding more particles later, )
        Ntot = Npz*Npr*Nptheta
        self.Ntot = Ntot
        self.q = q
        self.m = m
        self.n = n
        self.rmin = rmin
        self.rmax = rmax
        self.Npr = Npr
        self.Nptheta = Nptheta
        self.dens_func = dens_func
        self.continuous_injection = continuous_injection
        
        # Initialize the momenta
        self.uz = uz_m * np.ones(Ntot) + uz_th * np.random.normal(size=Ntot)
        self.ux = ux_m * np.ones(Ntot) + ux_th * np.random.normal(size=Ntot)
        self.uy = uy_m * np.ones(Ntot) + uy_th * np.random.normal(size=Ntot)
        self.inv_gamma = 1./np.sqrt(
            1 + self.ux**2 + self.uy**2 + self.uz**2 )

        # Initilialize the fields array (at the positions of the particles)
        self.Ez = np.zeros( Ntot )
        self.Ex = np.zeros( Ntot )
        self.Ey = np.zeros( Ntot )
        self.Bz = np.zeros( Ntot )
        self.Bx = np.zeros( Ntot )
        self.By = np.zeros( Ntot )

        # Allocate the positions and weights of the particles,
        # and fill them with values if the array is not empty
        self.x = np.empty( Ntot )
        self.y = np.empty( Ntot )
        self.z = np.empty( Ntot )
        self.w = np.empty( Ntot )
        
        if Ntot > 0 :
            # Get the 1d arrays of evenly-spaced positions for the particles
            dz = (zmax-zmin)*1./Npz
            z_reg =  zmin + dz*( np.arange(Npz) + 0.5 )
            dr = (rmax-rmin)*1./Npr
            r_reg =  rmin + dr*( np.arange(Npr) + 0.5 )
            dtheta = 2*np.pi/Nptheta
            theta_reg = dtheta * np.arange(Nptheta)

            # Get the corresponding particles positions
            # (copy=True is important here, since it allows to
            # change the angles individually)
            zp, rp, thetap = np.meshgrid( z_reg, r_reg, theta_reg, copy=True)
            # Prevent the particles from being aligned along any direction
            unalign_angles( thetap, Npr, Npz, method='random' )
            # Flatten them (This performs a memory copy)
            r = rp.flatten()
            self.x[:] = r * np.cos( thetap.flatten() )
            self.y[:] = r * np.sin( thetap.flatten() )
            self.z[:] = zp.flatten()

            # Get the weights (i.e. charge of each macroparticle), which
            # are equal to the density times the volume r d\theta dr dz
            self.w[:] = q * n * r * dtheta*dr*dz
            # Modulate it by the density profile
            if dens_func is not None :
                self.w[:] = self.w * dens_func( self.z, r )

        # Allocate arrays for the particles sorting when using CUDA
        self.cell_idx = np.empty( Ntot, dtype=np.int32)
        self.sorted_idx = np.arange( Ntot, dtype=np.uint32)
        # Allocate a buffer that is used to resort the particle arrays
        self.particle_buffer = np.arange( Ntot, dtype=np.float64 )
        # Register boolean that records if the particles are sorted or not
        self.sorted = False

    def send_particles_to_gpu( self ):
        """
        Copy the particles to the GPU.
        Particle arrays of self now point to the GPU arrays.
        """
        if self.use_cuda_memory:
            # Send positions, velocities, inverse gamma and weights
            # to the GPU (CUDA)
            self.x = cuda.to_device(self.x)
            self.y = cuda.to_device(self.y)
            self.z = cuda.to_device(self.z)
            self.ux = cuda.to_device(self.ux)
            self.uy = cuda.to_device(self.uy)
            self.uz = cuda.to_device(self.uz)
            self.inv_gamma = cuda.to_device(self.inv_gamma)
            self.w = cuda.to_device(self.w)

            # Initialize empty arrays on the GPU for the field
            # gathering and the particle push
            self.Ex = cuda.device_array_like(self.Ex)
            self.Ey = cuda.device_array_like(self.Ey)
            self.Ez = cuda.device_array_like(self.Ez)
            self.Bx = cuda.device_array_like(self.Bx)
            self.By = cuda.device_array_like(self.By)
            self.Bz = cuda.device_array_like(self.Bz)

            # Initialize empty arrays on the GPU for the sorting
            self.cell_idx = cuda.device_array_like(self.cell_idx)
            self.sorted_idx = cuda.device_array_like(self.sorted_idx)
            self.particle_buffer = cuda.device_array_like(self.particle_buffer)

    def receive_particles_from_gpu( self ):
        """
        Receive the particles from the GPU.
        Particle arrays are accessible by the CPU again.
        """
        if self.use_cuda_memory:
            # Copy the positions, velocities, inverse gamma and weights
            # to the GPU (CUDA)
            self.x = self.x.copy_to_host()
            self.y = self.y.copy_to_host()
            self.z = self.z.copy_to_host()
            self.ux = self.ux.copy_to_host()
            self.uy = self.uy.copy_to_host()
            self.uz = self.uz.copy_to_host()
            self.inv_gamma = self.inv_gamma.copy_to_host()
            self.w = self.w.copy_to_host()

            # Initialize empty arrays on the CPU for the field
            # gathering and the particle push
            self.Ex = np.zeros(self.Ntot, dtype = np.float64)
            self.Ey = np.zeros(self.Ntot, dtype = np.float64)
            self.Ez = np.zeros(self.Ntot, dtype = np.float64)
            self.Bx = np.zeros(self.Ntot, dtype = np.float64)
            self.By = np.zeros(self.Ntot, dtype = np.float64)
            self.Bz = np.zeros(self.Ntot, dtype = np.float64)

            # Initialize empty arrays on the CPU
            # that represent the sorting arrays
            self.cell_idx = np.empty(self.Ntot, dtype = np.int32)
            self.sorted_idx = np.arange(self.Ntot, dtype = np.uint32)
            self.particle_buffer = np.arange( self.Ntot, dtype = np.float64)

    def rearrange_particle_arrays( self ):
        """
        Rearranges the particle data arrays to match with the sorted
        cell index array. The sorted index array is used to resort the
        arrays. A particle buffer is used to temporarily store
        the rearranged data.
        """
        # Get the threads per block and the blocks per grid
        dim_grid_1d, dim_block_1d = cuda_tpb_bpg_1d( self.Ntot )
        # Iterate over particle attributes
        for attr in ['x', 'y', 'z', 'ux', 'uy', 'uz', 'w', 'inv_gamma']:
            # Get particle GPU array
            val = getattr(self, attr)
            # Write particle data to particle buffer array while rearranging
            write_particle_buffer[dim_grid_1d, dim_block_1d](
                self.sorted_idx, val, self.particle_buffer)
            # Assign the particle buffer to 
            # the initial particle data array 
            setattr(self, attr, self.particle_buffer)
            # Assign the old particle data array to
            # the particle buffer
            self.particle_buffer = val

    def push_p( self ) :
        """
        Advance the particles' momenta over one timestep, using the Vay pusher
        Reference : Vay, Physics of Plasmas 15, 056701 (2008)

        This assumes that the momenta (ux, uy, uz) are initially one
        half-timestep *behind* the positions (x, y, z), and it brings
        them one half-timestep *ahead* of the positions.
        """
        if self.use_numba :
            push_p_numba(self.ux, self.uy, self.uz, self.inv_gamma, 
                    self.Ex, self.Ey, self.Ez, self.Bx, self.By, self.Bz,
                    self.q, self.m, self.Ntot, self.dt )
        elif self.use_cuda :
            # Get the threads per block and the blocks per grid
            dim_grid_1d, dim_block_1d = cuda_tpb_bpg_1d( self.Ntot )
            # Call the CUDA Kernel for the particle push
            push_p_gpu[dim_grid_1d, dim_block_1d](
                    self.ux, self.uy, self.uz, self.inv_gamma,
                    self.Ex, self.Ey, self.Ez,
                    self.Bx, self.By, self.Bz,
                    self.q, self.m, self.Ntot, self.dt )
        else :
            push_p_numpy(self.ux, self.uy, self.uz, self.inv_gamma, 
                    self.Ex, self.Ey, self.Ez, self.Bx, self.By, self.Bz,
                    self.q, self.m, self.Ntot, self.dt )
        
    def halfpush_x( self ) :
        """
        Advance the particles' positions over one half-timestep
        
        This assumes that the positions (x, y, z) are initially either
        one half-timestep *behind* the momenta (ux, uy, uz), or at the
        same timestep as the momenta.
        """
        if self.use_cuda :
            # Get the threads per block and the blocks per grid
            dim_grid_1d, dim_block_1d = cuda_tpb_bpg_1d( self.Ntot )
            # Call the CUDA Kernel for halfpush in x
            push_x_gpu[dim_grid_1d, dim_block_1d](
                self.x, self.y, self.z,
                self.ux, self.uy, self.uz,
                self.inv_gamma, self.dt )
            # The particle array is unsorted after the push in x
            self.sorted = False
        else :
            push_x_numpy(self.x, self.y, self.z,
                self.ux, self.uy, self.uz,
                self.inv_gamma, self.dt )
        
    def gather( self, grid ) :
        """
        Gather the fields onto the macroparticles using numpy

        This assumes that the particle positions are currently at
        the same timestep as the field that is to be gathered.
        
        Parameter
        ----------
        grid : a list of InterpolationGrid objects
             (one InterpolationGrid object per azimuthal mode)
             Contains the field values on the interpolation grid
        """
        if self.use_cuda == True:
            # Get the threads per block and the blocks per grid
            dim_grid_1d, dim_block_1d = cuda_tpb_bpg_1d( self.Ntot )
            # Call the CUDA Kernel for the gathering of E and B Fields
            # for Mode 0 and 1 only.
            gather_field_gpu[dim_grid_1d, dim_block_1d](
                 self.x, self.y, self.z,
                 grid[0].invdz, grid[0].zmin, grid[0].Nz,
                 grid[0].invdr, grid[0].rmin, grid[0].Nr,
                 grid[0].Er, grid[0].Et, grid[0].Ez,
                 grid[1].Er, grid[1].Et, grid[1].Ez,
                 grid[0].Br, grid[0].Bt, grid[0].Bz,
                 grid[1].Br, grid[1].Bt, grid[1].Bz,
                 self.Ex, self.Ey, self.Ez,
                 self.Bx, self.By, self.Bz)
        else:
            # Preliminary arrays for the cylindrical conversion
            r = np.sqrt( self.x**2 + self.y**2 )
            # Avoid division by 0.
            invr = 1./np.where( r!=0., r, 1. )
            cos = np.where( r!=0., self.x*invr, 1. )
            sin = np.where( r!=0., self.y*invr, 0. )

            # Indices and weights
            iz_lower, iz_upper, Sz_lower, Sz_upper = linear_weights( self.z,
                grid[0].invdz, grid[0].zmin, grid[0].Nz, direction='z')
            ir_lower, ir_upper, Sr_lower, Sr_upper, Sr_guard = linear_weights(
                r, grid[0].invdr, grid[0].rmin, grid[0].Nr, direction='r' )

            # Number of modes considered :
            # number of elements in the grid list
            Nm = len(grid)
            
            # -------------------------------
            # Gather the E field mode by mode
            # -------------------------------
            # Zero the previous fields
            self.Ex[:] = 0.
            self.Ey[:] = 0.
            self.Ez[:] = 0.
            # Prepare auxiliary matrices
            Ft = np.zeros(self.Ntot)
            Fr = np.zeros(self.Ntot)
            exptheta = np.ones(self.Ntot, dtype='complex')
            # exptheta takes the value exp(-im theta) throughout the loop
            for m in range(Nm) :
                # Increment exptheta (notice the - : backward transform)
                if m==1 :
                    exptheta[:].real = cos
                    exptheta[:].imag = -sin
                elif m>1 :
                    exptheta[:] = exptheta*( cos - 1.j*sin )
                # Gather the fields
                # (The sign with which the guards are added
                # depends on whether the fields should be zero on axis)
                if self.use_numba:
                    # Use numba
                    gather_field_numba( exptheta, m, grid[m].Er, Fr, 
                        iz_lower, iz_upper, Sz_lower, Sz_upper,
                        ir_lower, ir_upper, Sr_lower, Sr_upper,
                        -(-1.)**m, Sr_guard )
                    gather_field_numba( exptheta, m, grid[m].Et, Ft, 
                        iz_lower, iz_upper, Sz_lower, Sz_upper,
                        ir_lower, ir_upper, Sr_lower, Sr_upper,
                        -(-1.)**m, Sr_guard )
                    gather_field_numba( exptheta, m, grid[m].Ez, self.Ez, 
                        iz_lower, iz_upper, Sz_lower, Sz_upper,
                        ir_lower, ir_upper, Sr_lower, Sr_upper,
                        (-1.)**m, Sr_guard )
                else:
                    # Use numpy (slower)
                    gather_field_numpy( exptheta, m, grid[m].Er, Fr, 
                        iz_lower, iz_upper, Sz_lower, Sz_upper,
                        ir_lower, ir_upper, Sr_lower, Sr_upper,
                        -(-1.)**m, Sr_guard )
                    gather_field_numpy( exptheta, m, grid[m].Et, Ft, 
                        iz_lower, iz_upper, Sz_lower, Sz_upper,
                        ir_lower, ir_upper, Sr_lower, Sr_upper,
                        -(-1.)**m, Sr_guard )
                    gather_field_numpy( exptheta, m, grid[m].Ez, self.Ez, 
                        iz_lower, iz_upper, Sz_lower, Sz_upper,
                        ir_lower, ir_upper, Sr_lower, Sr_upper,
                        (-1.)**m, Sr_guard )

            # Convert to Cartesian coordinates
            self.Ex[:] = cos*Fr - sin*Ft
            self.Ey[:] = sin*Fr + cos*Ft

            # -------------------------------
            # Gather the B field mode by mode
            # -------------------------------
            # Zero the previous fields
            self.Bx[:] = 0.
            self.By[:] = 0.
            self.Bz[:] = 0.
            # Prepare auxiliary matrices
            Ft[:] = 0.
            Fr[:] = 0.
            exptheta[:] = 1.
            # exptheta takes the value exp(-im theta) throughout the loop
            for m in range(Nm) :
                # Increment exptheta (notice the - : backward transform)
                if m==1 :
                    exptheta[:].real = cos
                    exptheta[:].imag = -sin
                elif m>1 :
                    exptheta[:] = exptheta*( cos - 1.j*sin )
                # Gather the fields
                # (The sign with which the guards are added
                # depends on whether the fields should be zero on axis)
                if self.use_numba:
                    # Use numba
                    gather_field_numba( exptheta, m, grid[m].Br, Fr, 
                        iz_lower, iz_upper, Sz_lower, Sz_upper,
                        ir_lower, ir_upper, Sr_lower, Sr_upper,
                        -(-1.)**m, Sr_guard )
                    gather_field_numba( exptheta, m, grid[m].Bt, Ft, 
                        iz_lower, iz_upper, Sz_lower, Sz_upper,
                        ir_lower, ir_upper, Sr_lower, Sr_upper,
                        -(-1.)**m, Sr_guard )
                    gather_field_numba( exptheta, m, grid[m].Bz, self.Bz, 
                        iz_lower, iz_upper, Sz_lower, Sz_upper,
                        ir_lower, ir_upper, Sr_lower, Sr_upper,
                        (-1.)**m, Sr_guard )
                else:
                    # Use numpy (slower)
                    gather_field_numpy( exptheta, m, grid[m].Br, Fr, 
                        iz_lower, iz_upper, Sz_lower, Sz_upper,
                        ir_lower, ir_upper, Sr_lower, Sr_upper,
                        -(-1.)**m, Sr_guard )
                    gather_field_numpy( exptheta, m, grid[m].Bt, Ft, 
                        iz_lower, iz_upper, Sz_lower, Sz_upper,
                        ir_lower, ir_upper, Sr_lower, Sr_upper,
                        -(-1.)**m, Sr_guard )
                    gather_field_numpy( exptheta, m, grid[m].Bz, self.Bz, 
                        iz_lower, iz_upper, Sz_lower, Sz_upper,
                        ir_lower, ir_upper, Sr_lower, Sr_upper,
                        (-1.)**m, Sr_guard )
            # Convert to Cartesian coordinates
            self.Bx[:] = cos*Fr - sin*Ft
            self.By[:] = sin*Fr + cos*Ft

        
    def deposit( self, fld, fieldtype ) :
        """
        Deposit the particles charge or current onto the grid, using numpy
        
        This assumes that the particle positions (and momenta in the case of J)
        are currently at the same timestep as the field that is to be deposited
        
        Parameter
        ----------
        fld : a Field object 
             Contains the list of InterpolationGrid objects with
             the field values as well as the prefix sum.

        fieldtype : string
             Indicates which field to deposit
             Either 'J' or 'rho'
        """
        # Shortcut for the list of InterpolationGrid objects
        grid = fld.interp

        if self.use_cuda == True:
            # Get the threads per block and the blocks per grid
            dim_grid_2d_flat, dim_block_2d_flat = cuda_tpb_bpg_1d(
                                                    grid[0].Nz*grid[0].Nr )
            dim_grid_2d, dim_block_2d = cuda_tpb_bpg_2d( 
                                          grid[0].Nz, grid[0].Nr )

            # Create the helper arrays for deposition
            d_F0, d_F1, d_F2, d_F3 = cuda_deposition_arrays( 
                grid[0].Nz, grid[0].Nr, fieldtype = fieldtype )

            # Sort the particles
            if self.sorted == False:
                self.sort_particles(fld = fld)
                # The particles are now sorted and rearranged
                self.sorted = True

            # Call the CUDA Kernel for the deposition of rho or J
            # for Mode 0 and 1 only.
            # Rho
            if fieldtype == 'rho':
                # Deposit rho in each of four directions
                deposit_rho_gpu[dim_grid_2d_flat, dim_block_2d_flat](
                    self.x, self.y, self.z, self.w, 
                    grid[0].invdz, grid[0].zmin, grid[0].Nz, 
                    grid[0].invdr, grid[0].rmin, grid[0].Nr,
                    d_F0, d_F1, d_F2, d_F3,
                    self.cell_idx, fld.d_prefix_sum)
                # Add the four directions together
                add_rho[dim_grid_2d, dim_block_2d](
                    grid[0].rho, grid[1].rho,
                    d_F0, d_F1, d_F2, d_F3)
            # J
            elif fieldtype == 'J':
                # Deposit J in each of four directions
                deposit_J_gpu[dim_grid_2d_flat, dim_block_2d_flat](
                    self.x, self.y, self.z, self.w,
                    self.ux, self.uy, self.uz, self.inv_gamma,
                    grid[0].invdz, grid[0].zmin, grid[0].Nz, 
                    grid[0].invdr, grid[0].rmin, grid[0].Nr,
                    d_F0, d_F1, d_F2, d_F3,
                    self.cell_idx, fld.d_prefix_sum)
                # Add the four directions together
                add_J[dim_grid_2d, dim_block_2d](
                    grid[0].Jr, grid[1].Jr,
                    grid[0].Jt, grid[1].Jt,
                    grid[0].Jz, grid[1].Jz,
                    d_F0, d_F1, d_F2, d_F3)
            else :
                raise ValueError(
        "`fieldtype` should be either 'J' or 'rho', but is `%s`" %fieldtype )

        # CPU version
        else:       
            # Preliminary arrays for the cylindrical conversion
            r = np.sqrt( self.x**2 + self.y**2 )
            # Avoid division by 0.
            invr = 1./np.where( r!=0., r, 1. )
            cos = np.where( r!=0., self.x*invr, 1. )
            sin = np.where( r!=0., self.y*invr, 0. )

            # Indices and weights
            iz_lower, iz_upper, Sz_lower, Sz_upper = linear_weights( 
                self.z, grid[0].invdz, grid[0].zmin, grid[0].Nz, direction='z')
            ir_lower, ir_upper, Sr_lower, Sr_upper, Sr_guard = linear_weights(
                r, grid[0].invdr, grid[0].rmin, grid[0].Nr, direction='r')

            # Number of modes considered :
            # number of elements in the grid list
            Nm = len(grid)

            if fieldtype == 'rho' :
                # ---------------------------------------
                # Deposit the charge density mode by mode
                # ---------------------------------------
                # Prepare auxiliary matrix
                exptheta = np.ones( self.Ntot, dtype='complex')
                # exptheta takes the value exp(im theta) throughout the loop
                for m in range(Nm) :
                    # Increment exptheta (notice the + : forward transform)
                    if m==1 :
                        exptheta[:].real = cos
                        exptheta[:].imag = sin
                    elif m>1 :
                        exptheta[:] = exptheta*( cos + 1.j*sin )
                    # Deposit the fields
                    # (The sign -1 with which the guards are added is not
                    # trivial to derive but avoids artifacts on the axis)
                    if self.use_numba :
                        # Use numba
                        deposit_field_numba( self.w*exptheta, grid[m].rho, 
                            iz_lower, iz_upper, Sz_lower, Sz_upper,
                            ir_lower, ir_upper, Sr_lower, Sr_upper,
                            -1., Sr_guard )
                    else:
                        # Use numpy (slower)
                        deposit_field_numpy( self.w*exptheta, grid[m].rho, 
                            iz_lower, iz_upper, Sz_lower, Sz_upper,
                            ir_lower, ir_upper, Sr_lower, Sr_upper,
                            -1., Sr_guard )

            elif fieldtype == 'J' :
                # ----------------------------------------
                # Deposit the current density mode by mode
                # ----------------------------------------
                # Calculate the currents
                Jr = self.w * c * self.inv_gamma*( cos*self.ux + sin*self.uy )
                Jt = self.w * c * self.inv_gamma*( cos*self.uy - sin*self.ux )
                Jz = self.w * c * self.inv_gamma*self.uz
                # Prepare auxiliary matrix
                exptheta = np.ones( self.Ntot, dtype='complex')
                # exptheta takes the value exp(im theta) throughout the loop
                for m in range(Nm) :
                    # Increment exptheta (notice the + : forward transform)
                    if m==1 :
                        exptheta[:].real = cos
                        exptheta[:].imag = sin
                    elif m>1 :
                        exptheta[:] = exptheta*( cos + 1.j*sin )
                    # Deposit the fields
                    # (The sign -1 with which the guards are added is not
                    # trivial to derive but avoids artifacts on the axis)
                    if self.use_numba:
                        # Use numba
                        deposit_field_numba( Jr*exptheta, grid[m].Jr, 
                            iz_lower, iz_upper, Sz_lower, Sz_upper,
                            ir_lower, ir_upper, Sr_lower, Sr_upper,
                            -1., Sr_guard )
                        deposit_field_numba( Jt*exptheta, grid[m].Jt, 
                            iz_lower, iz_upper, Sz_lower, Sz_upper,
                            ir_lower, ir_upper, Sr_lower, Sr_upper,
                            -1., Sr_guard )
                        deposit_field_numba( Jz*exptheta, grid[m].Jz, 
                            iz_lower, iz_upper, Sz_lower, Sz_upper,
                            ir_lower, ir_upper, Sr_lower, Sr_upper,
                            -1., Sr_guard )
                    else:
                        # Use numpy (slower)
                        deposit_field_numpy( Jr*exptheta, grid[m].Jr, 
                            iz_lower, iz_upper, Sz_lower, Sz_upper,
                            ir_lower, ir_upper, Sr_lower, Sr_upper,
                            -1., Sr_guard )
                        deposit_field_numpy( Jt*exptheta, grid[m].Jt, 
                            iz_lower, iz_upper, Sz_lower, Sz_upper,
                            ir_lower, ir_upper, Sr_lower, Sr_upper,
                            -1., Sr_guard )
                        deposit_field_numpy( Jz*exptheta, grid[m].Jz, 
                            iz_lower, iz_upper, Sz_lower, Sz_upper,
                            ir_lower, ir_upper, Sr_lower, Sr_upper,
                            -1., Sr_guard )
            else :
                raise ValueError(
        "`fieldtype` should be either 'J' or 'rho', but is `%s`" %fieldtype )

    def sort_particles(self, fld):
        """
        Sort the particles by performing the following steps:
        1. Get fied cell index
        2. Sort field cell index
        3. Parallel prefix sum
        4. Rearrange particle arrays
        
        Parameter
        ----------
        fld : a Field object 
             Contains the list of InterpolationGrid objects with
             the field values as well as the prefix sum.
        """
        # Shortcut for interpolation grids
        grid = fld.interp
        # Get the threads per block and the blocks per grid
        dim_grid_1d, dim_block_1d = cuda_tpb_bpg_1d( self.Ntot )
        dim_grid_2d_flat, dim_block_2d_flat = cuda_tpb_bpg_1d(
                                                grid[0].Nz*grid[0].Nr )
        # ------------------------
        # Sorting of the particles
        # ------------------------
        # Get the cell index of each particle 
        # (defined by iz_lower and ir_lower)
        get_cell_idx_per_particle[dim_grid_1d, dim_block_1d](
            self.cell_idx,
            self.sorted_idx, 
            self.x, self.y, self.z, 
            grid[0].invdz, grid[0].zmin, grid[0].Nz, 
            grid[0].invdr, grid[0].rmin, grid[0].Nr)
        # Sort the cell index array and modify the sorted_idx array
        # accordingly. The value of the sorted_idx array corresponds 
        # to the index of the sorted particle in the other particle 
        # arrays.
        sort_particles_per_cell(self.cell_idx, self.sorted_idx)
        # Reset the old prefix sum
        reset_prefix_sum[dim_grid_2d_flat, dim_block_2d_flat](
            fld.d_prefix_sum)
        # Perform the inclusive parallel prefix sum
        incl_prefix_sum[dim_grid_1d, dim_block_1d](
            self.cell_idx, fld.d_prefix_sum)
        # Rearrange the particle arrays
        self.rearrange_particle_arrays()
