How to run the code
===================

Once installed (see :doc:`install/installation`), FBPIC is available as a **Python
module** on your system. Thus, a simulation is setup by creating a
**Python script** that imports and uses FBPIC's functionalities.

Script examples
----------------

You can download examples of FBPIC scripts below (which you can then modify
to suit your needs):

.. toctree::
    :maxdepth: 1

    example_input/lwfa_script.rst
    example_input/ionization_script.rst
    example_input/boosted_frame_script.rst

(See the documentation of :any:`Particles.make_ionizable` for more information on ionization,
and the section :doc:`advanced/boosted_frame` for more information on the boosted frame.)

The different FBPIC objects that are used in the above simulation scripts are
defined in the section :doc:`api_reference/api_reference`.

Running the simulation
----------------------

The simulation is then run by typing

::

   python fbpic_script.py

where ``fbpic_script.py`` should be replaced by the name of your
Python script: either ``lwfa_script.py`` or
``boosted_frame_script.py`` for the above examples.

.. note::

   When running on CPU, **multi-threading** is enabled by default, and the
   default number of threads is the number of cores on your system. You
   can modify this with environment variables:

   - To modify the number of threads (e.g. set it to 8 threads):

   ::

    export MKL_NUM_THREADS=8
    export NUMBA_NUM_THREADS=8
    python fbpic_script.py

   - To disable multi-threading altogether:

   ::

    export FBPIC_DISABLE_THREADING=1
    export MKL_NUM_THREADS=1
    export NUMBA_NUM_THREADS=1
    python fbpic_script.py

   It can also happen that an alternative threading backend is selected by Numba
   during installation. It is therefore sometimes required to set
   ``OMP_NUM_THREADS`` in addition to (or instead of) ``MKL_NUM_THREADS``.

   When running in a Jupyter notebook, environment variables can be set by
   executing the following command at the beginning of the notebook:

   ::

    import os
    os.environ['MKL_NUM_THREADS']='1'

.. note::

  When running on GPU with MPI domain decomposition, it is possible to enable
  the CUDA GPUDirect technology. GPUDirect enables direct communication of
  CUDA device arrays between GPUs over MPI without explicitly copying the data
  to CPU first, resulting in reduced latencies and increased bandwidth. As this
  feature requires a CUDA-aware MPI implementation that supports GPUDirect,
  it is disabled by default and should be used with care.

  To activate this feature, the user needs to set the following
  environment variable:

  ::

    export FBPIC_ENABLE_GPUDIRECT=1


Visualizing the simulation results
----------------------------------

The code outputs HDF5 files, that comply with the
`openPMD standard <http://www.openpmd.org/#/start>`_. As such, they
can be visualized for instance with the `openPMD-viewer
<https://github.com/openPMD/openPMD-viewer>`_). To do so, first
install the openPMD-viewer by typing

::

   conda install -c rlehe openpmd_viewer

And then type

::

   openPMD_notebook

and follow the instructions in the notebook that pops up. (NB: the
notebook only shows some of the capabilities of the openPMD-viewer. To
learn more, see the tutorial notebook on the  `Github repository
<https://github.com/openPMD/openPMD-viewer>`_ of openPMD-viewer).
