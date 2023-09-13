#!/bin/bash -ef

STD_ARGS="--progress-bar off --upgrade"
EXTRA_ARGS=""
if [ ! -z "$CONDA_ENV" ]; then
	echo "Uninstalling MNE for CONDA_ENV=${CONDA_ENV}"
	conda remove -c conda-forge --force -yq mne
	python -m pip uninstall -y mne
elif [ ! -z "$CONDA_DEPENDENCIES" ]; then
	echo "Using Mamba to install CONDA_DEPENDENCIES=${CONDA_DEPENDENCIES}"
	mamba install -y $CONDA_DEPENDENCIES
else
	echo "Install pip-pre dependencies"
	test "${MNE_CI_KIND}" == "pip-pre"
	python -m pip install $STD_ARGS pip setuptools wheel packaging
	echo "Numpy"
	pip uninstall -yq numpy
	echo "PyQt6"
	pip install $STD_ARGS --pre --only-binary ":all:" --default-timeout=60 --extra-index-url https://www.riverbankcomputing.com/pypi/simple PyQt6
	echo "NumPy/SciPy/pandas etc."
	pip install $STD_ARGS --pre --only-binary ":all:" --default-timeout=60 --extra-index-url "https://pypi.anaconda.org/scientific-python-nightly-wheels/simple" "numpy>=2.0.0.dev0" scipy scikit-learn pandas matplotlib pillow statsmodels
	echo "dipy"
	pip install $STD_ARGS --pre --only-binary ":all:" --default-timeout=60 --extra-index-url "https://pypi.anaconda.org/scipy-wheels-nightly/simple" dipy
	echo "H5py"
	pip install $STD_ARGS --pre --only-binary ":all:" -f "https://7933911d6844c6c53a7d-47bd50c35cd79bd838daf386af554a83.ssl.cf2.rackcdn.com" h5py
	echo "OpenMEEG"
	pip install $STD_ARGS --pre --only-binary ":all:" --extra-index-url "https://test.pypi.org/simple" openmeeg
	# No Numba because it forces an old NumPy version
	echo "nilearn and openmeeg"
	pip install $STD_ARGS --pre git+https://github.com/nilearn/nilearn
	echo "VTK"
	pip install $STD_ARGS --pre --only-binary ":all:" --extra-index-url "https://wheels.vtk.org" vtk
	python -c "import vtk"
	echo "PyVista"
	pip install --progress-bar off git+https://github.com/pyvista/pyvista
	echo "pyvistaqt"
	pip install --progress-bar off git+https://github.com/pyvista/pyvistaqt
	echo "imageio-ffmpeg, xlrd, mffpy, python-picard"
	pip install --progress-bar off --pre imageio-ffmpeg xlrd mffpy python-picard patsy
	echo "mne-qt-browser"
	pip install --progress-bar off git+https://github.com/mne-tools/mne-qt-browser
	echo "nibabel with workaround"
	pip install --progress-bar off --pre git+https://github.com/mscheltienne/nibabel.git@np.sctypes
	EXTRA_ARGS="--pre"
fi
echo ""

# for compat_minimal and compat_old, we don't want to --upgrade
if [ ! -z "$CONDA_DEPENDENCIES" ]; then
	echo "Installing dependencies for conda"
	python -m pip install -r requirements_base.txt -r requirements_testing.txt
else
	echo "Installing dependencies using pip"
	python -m pip install $STD_ARGS $EXTRA_ARGS -r requirements_base.txt -r requirements_testing.txt -r requirements_hdf5.txt
fi
echo ""

if [ "${DEPS}" != "minimal" ]; then
	echo "Installing non-minimal dependencies"
	python -m pip install $STD_ARGS $EXTRA_ARGS -r requirements_testing_extra.txt
fi
