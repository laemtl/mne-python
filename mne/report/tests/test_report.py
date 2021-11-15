# -*- coding: utf-8 -*-
# Authors: Mainak Jas <mainak@neuro.hut.fi>
#          Teon Brooks <teon.brooks@gmail.com>
#
# License: BSD-3-Clause

from pathlib import Path
import base64
import copy
import glob
import pickle
from io import BytesIO
import os
import os.path as op
import re
import shutil

import numpy as np
import pytest
from matplotlib import pyplot as plt

from mne import Epochs, read_events, read_evokeds, read_cov, pick_channels_cov
from mne.report import report as report_mod
from mne.report.report import CONTENT_ORDER
from mne.io import read_raw_fif
from mne.datasets import testing
from mne.report import Report, open_report, _ReportScraper, report
from mne.utils import requires_nibabel, Bunch, requires_h5py, requires_sklearn
from mne.viz import plot_alignment
from mne.io.write import DATE_NONE
from mne.preprocessing import ICA


data_dir = testing.data_path(download=False)
subjects_dir = op.join(data_dir, 'subjects')
sample_meg_dir = op.join(data_dir, 'MEG', 'sample')
raw_fname = op.join(sample_meg_dir, 'sample_audvis_trunc_raw.fif')
ms_fname = op.join(data_dir, 'SSS', 'test_move_anon_raw.fif')
events_fname = op.join(sample_meg_dir, 'sample_audvis_trunc_raw-eve.fif')
evoked_fname = op.join(sample_meg_dir, 'sample_audvis_trunc-ave.fif')
cov_fname = op.join(sample_meg_dir, 'sample_audvis_trunc-cov.fif')
ecg_proj_fname = op.join(sample_meg_dir, 'sample_audvis_ecg-proj.fif')
eog_proj_fname = op.join(sample_meg_dir, 'sample_audvis_eog-proj.fif')
fwd_fname = op.join(
    sample_meg_dir, 'sample_audvis_trunc-meg-eeg-oct-6-fwd.fif'
)
trans_fname = op.join(sample_meg_dir, 'sample_audvis_trunc-trans.fif')
inv_fname = op.join(
    sample_meg_dir, 'sample_audvis_trunc-meg-eeg-oct-6-meg-inv.fif'
)
stc_fname = op.join(sample_meg_dir, 'sample_audvis_trunc-meg')
mri_fname = op.join(subjects_dir, 'sample', 'mri', 'T1.mgz')
bdf_fname = op.realpath(op.join(op.dirname(__file__), '..', '..', 'io',
                                'edf', 'tests', 'data', 'test.bdf'))
edf_fname = op.realpath(op.join(op.dirname(__file__), '..', '..', 'io',
                                'edf', 'tests', 'data', 'test.edf'))

base_dir = op.realpath(op.join(op.dirname(__file__), '..', '..', 'io', 'tests',
                               'data'))
evoked_fname = op.join(base_dir, 'test-ave.fif')

nirs_fname = op.join(data_dir, 'SNIRF', 'NIRx', 'NIRSport2', '1.0.3',
                     '2021-05-05_001.snirf')
stc_plot_kwargs = dict(  # for speed
    smoothing_steps=1, size=(300, 300), views='lat', hemi='lh')
topomap_kwargs = dict(res=8, contours=0, sensors=False)


def _get_example_figures():
    """Create two example figures."""
    fig1 = plt.plot([1, 2], [1, 2])[0].figure
    fig2 = plt.plot([3, 4], [3, 4])[0].figure
    return [fig1, fig2]


@pytest.fixture
def invisible_fig(monkeypatch):
    """Make objects invisible to speed up draws."""
    orig = report._fig_to_img

    def _make_invisible(fig, **kwargs):
        if isinstance(fig, plt.Figure):
            for ax in fig.axes:
                for attr in ('lines', 'collections', 'patches', 'images',
                             'texts'):
                    for item in getattr(ax, attr):
                        item.set_visible(False)
                ax.axis('off')
        return orig(fig, **kwargs)

    monkeypatch.setattr(report, '_fig_to_img', _make_invisible)
    yield


@pytest.mark.slowtest
@testing.requires_testing_data
def test_render_report(renderer_pyvistaqt, tmp_path, invisible_fig):
    """Test rendering *.fif files for mne report."""
    tempdir = str(tmp_path)
    raw_fname_new = op.join(tempdir, 'temp_raw.fif')
    raw_fname_new_bids = op.join(tempdir, 'temp_meg.fif')
    ms_fname_new = op.join(tempdir, 'temp_ms_raw.fif')
    event_fname_new = op.join(tempdir, 'temp_raw-eve.fif')
    cov_fname_new = op.join(tempdir, 'temp_raw-cov.fif')
    proj_fname_new = op.join(tempdir, 'temp_ecg-proj.fif')
    fwd_fname_new = op.join(tempdir, 'temp_raw-fwd.fif')
    inv_fname_new = op.join(tempdir, 'temp_raw-inv.fif')
    nirs_fname_new = op.join(tempdir, 'temp_raw-nirs.snirf')
    for a, b in [[raw_fname, raw_fname_new],
                 [raw_fname, raw_fname_new_bids],
                 [ms_fname, ms_fname_new],
                 [events_fname, event_fname_new],
                 [cov_fname, cov_fname_new],
                 [ecg_proj_fname, proj_fname_new],
                 [fwd_fname, fwd_fname_new],
                 [inv_fname, inv_fname_new],
                 [nirs_fname, nirs_fname_new]]:
        shutil.copyfile(a, b)

    # create and add -epo.fif and -ave.fif files
    epochs_fname = op.join(tempdir, 'temp-epo.fif')
    evoked_fname = op.join(tempdir, 'temp-ave.fif')
    # Speed it up by picking channels
    raw = read_raw_fif(raw_fname_new)
    raw.pick_channels(['MEG 0111', 'MEG 0121', 'EEG 001', 'EEG 002'])
    raw.del_proj()
    raw.set_eeg_reference(projection=True).load_data()
    epochs = Epochs(raw, read_events(events_fname), 1, -0.2, 0.2)
    epochs.save(epochs_fname, overwrite=True)
    # This can take forever, so let's make it fast
    # Also, make sure crop range is wide enough to avoid rendering bug
    evoked = epochs.average()
    with pytest.warns(RuntimeWarning, match='tmax is not in Evoked'):
        evoked.crop(0.1, 0.2)
    evoked.save(evoked_fname)

    report = Report(info_fname=raw_fname_new, subjects_dir=subjects_dir,
                    projs=False, image_format='png')
    with pytest.warns(RuntimeWarning, match='Cannot render MRI'):
        report.parse_folder(data_path=tempdir, on_error='raise',
                            n_time_points_evokeds=2, raw_butterfly=False,
                            stc_plot_kwargs=stc_plot_kwargs,
                            topomap_kwargs=topomap_kwargs)
    assert repr(report)

    # Check correct paths and filenames
    fnames = glob.glob(op.join(tempdir, '*.fif'))
    fnames.extend(glob.glob(op.join(tempdir, '*.snirf')))

    titles = [op.basename(x) for x in fnames if not x.endswith('-ave.fif')]
    titles.append(f'{op.basename(evoked_fname)}: {evoked.comment}')

    content_names = [element.name for element in report._content]
    for title in titles:
        assert title in content_names
        assert (''.join(report.html).find(title) != -1)

    assert len(report._content) == len(fnames)

    # Check saving functionality
    report.data_path = tempdir
    fname = op.join(tempdir, 'report.html')
    report.save(fname=fname, open_browser=False)
    assert (op.isfile(fname))
    html = Path(fname).read_text(encoding='utf-8')
    # Evoked in `evoked_fname`
    assert f'{op.basename(evoked_fname)}: {evoked.comment}' in html
    assert 'Topographies' in html
    assert 'Global field power' in html

    assert len(report._content) == len(fnames)

    # Check saving same report to new filename
    report.save(fname=op.join(tempdir, 'report2.html'), open_browser=False)
    assert (op.isfile(op.join(tempdir, 'report2.html')))

    # Check overwriting file
    report.save(fname=op.join(tempdir, 'report.html'), open_browser=False,
                overwrite=True)
    assert (op.isfile(op.join(tempdir, 'report.html')))

    # Check pattern matching with multiple patterns
    pattern = ['*proj.fif', '*eve.fif']
    with pytest.warns(RuntimeWarning, match='Cannot render MRI'):
        report.parse_folder(data_path=tempdir, pattern=pattern,
                            raw_butterfly=False)
    assert (repr(report))

    fnames = glob.glob(op.join(tempdir, '*.raw')) + \
        glob.glob(op.join(tempdir, '*.raw'))

    content_names = [element.name for element in report._content]
    for fname in fnames:
        assert (op.basename(fname) in
                [op.basename(x) for x in content_names])
        assert (''.join(report.html).find(op.basename(fname)) != -1)

    with pytest.raises(ValueError, match='Invalid value'):
        Report(image_format='foo')
    with pytest.raises(ValueError, match='Invalid value'):
        Report(image_format=None)

    # ndarray support smoke test
    report.add_figure(fig=np.zeros((2, 3, 3)), title='title')

    with pytest.raises(TypeError, match='It seems you passed a path'):
        report.add_figure(fig='foo', title='title')


@testing.requires_testing_data
def test_render_report_extra(renderer_pyvistaqt, tmp_path, invisible_fig):
    """Test SVG and projector rendering separately."""
    # ... otherwise things are very slow
    tempdir = str(tmp_path)
    raw_fname_new = op.join(tempdir, 'temp_raw.fif')
    shutil.copyfile(raw_fname, raw_fname_new)
    report = Report(info_fname=raw_fname_new, subjects_dir=subjects_dir,
                    projs=True, image_format='svg')
    with pytest.warns(RuntimeWarning, match='Cannot render MRI'):
        report.parse_folder(data_path=tempdir, on_error='raise',
                            n_time_points_evokeds=2, raw_butterfly=False,
                            stc_plot_kwargs=stc_plot_kwargs,
                            topomap_kwargs=topomap_kwargs)
    assert repr(report)
    report.data_path = tempdir
    fname = op.join(tempdir, 'report.html')
    report.save(fname=fname, open_browser=False)
    assert op.isfile(fname)
    html = Path(fname).read_text(encoding='utf-8')
    # Projectors in Raw.info
    assert 'SSP Projectors' in html


def test_add_custom_css(tmp_path):
    """Test adding custom CSS rules to the report."""
    tempdir = str(tmp_path)
    fname = op.join(tempdir, 'report.html')
    fig = plt.figure()  # Empty figure

    report = Report()
    report.add_figure(fig=fig, title='Test section')
    custom_css = '.report_custom { color: red; }'
    report.add_custom_css(css=custom_css)

    assert custom_css in report.include
    report.save(fname, open_browser=False)
    html = Path(fname).read_text(encoding='utf-8')
    assert custom_css in html


def test_add_custom_js(tmp_path):
    """Test adding custom JavaScript to the report."""
    tempdir = str(tmp_path)
    fname = op.join(tempdir, 'report.html')
    fig = plt.figure()  # Empty figure

    report = Report()
    report.add_figure(fig=fig, title='Test section')
    custom_js = ('function hello() {\n'
                 '  alert("Hello, report!");\n'
                 '}')
    report.add_custom_js(js=custom_js)

    assert custom_js in report.include
    report.save(fname, open_browser=False)
    html = Path(fname).read_text(encoding='utf-8')
    assert custom_js in html


@testing.requires_testing_data
def test_render_non_fiff(tmp_path):
    """Test rendering non-FIFF files for mne report."""
    tempdir = str(tmp_path)
    fnames_in = [bdf_fname, edf_fname]
    fnames_out = []
    for fname in fnames_in:
        basename = op.basename(fname)
        basename, ext = op.splitext(basename)
        fname_out = f'{basename}_raw{ext}'
        outpath = op.join(tempdir, fname_out)
        shutil.copyfile(fname, outpath)
        fnames_out.append(fname_out)

    report = Report()
    report.parse_folder(data_path=tempdir, render_bem=False, on_error='raise',
                        raw_butterfly=False)

    # Check correct paths and filenames
    content_names = [element.name for element in report._content]
    for fname in fnames_out:
        assert (op.basename(fname) in
                [op.basename(x) for x in content_names])

    assert len(report._content) == len(fnames_out)

    report.data_path = tempdir
    fname = op.join(tempdir, 'report.html')
    report.save(fname=fname, open_browser=False)
    html = Path(fname).read_text(encoding='utf-8')

    assert 'test_raw.bdf' in html
    assert 'test_raw.edf' in html


@testing.requires_testing_data
def test_report_raw_psd_and_date(tmp_path):
    """Test report raw PSD and DATE_NONE functionality."""
    with pytest.raises(TypeError, match='dict'):
        Report(raw_psd='foo')

    tempdir = str(tmp_path)
    raw = read_raw_fif(raw_fname).crop(0, 1.).load_data()
    raw.info['experimenter'] = 'mne test'
    raw.info['subject_info'] = dict(id=123, his_id='sample')

    raw_fname_new = op.join(tempdir, 'temp_raw.fif')
    raw.save(raw_fname_new)
    report = Report(raw_psd=True)
    report.parse_folder(data_path=tempdir, render_bem=False,
                        on_error='raise', raw_butterfly=False)
    assert isinstance(report.html, list)
    assert 'PSD' in ''.join(report.html)
    assert 'Unknown' not in ''.join(report.html)
    assert 'GMT' in ''.join(report.html)

    # test new anonymize functionality
    report = Report()
    raw.anonymize()
    raw.save(raw_fname_new, overwrite=True)
    report.parse_folder(data_path=tempdir, render_bem=False,
                        on_error='raise', raw_butterfly=False)
    assert isinstance(report.html, list)
    assert 'Unknown' not in ''.join(report.html)

    # DATE_NONE functionality
    report = Report()
    # old style (pre 0.20) date anonymization
    with raw.info._unlock():
        raw.info['meas_date'] = None
    for key in ('file_id', 'meas_id'):
        value = raw.info.get(key)
        if value is not None:
            assert 'msecs' not in value
            value['secs'] = DATE_NONE[0]
            value['usecs'] = DATE_NONE[1]
    raw.save(raw_fname_new, overwrite=True)
    report.parse_folder(data_path=tempdir, render_bem=False,
                        on_error='raise', raw_butterfly=False)
    assert isinstance(report.html, list)
    assert 'Unknown' in ''.join(report.html)


@pytest.mark.slowtest  # slow for Mayavi on Azure
@testing.requires_testing_data
def test_render_add_sections(renderer, tmp_path):
    """Test adding figures/images to section."""
    tempdir = str(tmp_path)
    report = Report(subjects_dir=subjects_dir)
    # Check add_figure functionality
    fig = plt.plot([1, 2], [1, 2])[0].figure

    report.add_figure(fig=fig, title='evoked response', image_format='svg')
    assert 'caption' not in report._content[-1].html

    report.add_figure(fig=fig, title='evoked with caption', caption='descr')
    assert 'caption' in report._content[-1].html

    # Check add_image with png
    img_fname = op.join(tempdir, 'testimage.png')
    fig.savefig(img_fname)
    report.add_image(image=img_fname, title='evoked response')

    with pytest.raises(FileNotFoundError, match='No such file or directory'):
        report.add_image(image='foobar.xxx', title='H')

    evoked = read_evokeds(evoked_fname, condition='Left Auditory',
                          baseline=(-0.2, 0.0))
    fig = plot_alignment(evoked.info, trans_fname, subject='sample',
                         subjects_dir=subjects_dir)

    report.add_figure(fig=fig, title='random image')
    assert (repr(report))
    fname = op.join(str(tmp_path), 'test.html')
    report.save(fname, open_browser=False)

    assert len(report) == 4


@pytest.mark.slowtest
@testing.requires_testing_data
@requires_nibabel()
def test_render_mri(renderer, tmp_path):
    """Test rendering MRI for mne report."""
    tempdir = str(tmp_path)
    trans_fname_new = op.join(tempdir, 'temp-trans.fif')
    for a, b in [[trans_fname, trans_fname_new]]:
        shutil.copyfile(a, b)
    report = Report(info_fname=raw_fname,
                    subject='sample', subjects_dir=subjects_dir)
    report.parse_folder(data_path=tempdir, mri_decim=30, pattern='*')
    fname = op.join(tempdir, 'report.html')
    report.save(fname, open_browser=False)
    html = Path(fname).read_text(encoding='utf-8')
    assert 'data-mne-tags=" bem "' in html
    assert repr(report)
    report.add_bem(subject='sample', title='extra', tags=('foo',),
                   subjects_dir=subjects_dir, decim=30)
    report.save(fname, open_browser=False, overwrite=True)
    html = Path(fname).read_text(encoding='utf-8')
    assert 'data-mne-tags=" bem "' in html
    assert 'data-mne-tags=" foo "' in html


@testing.requires_testing_data
@requires_nibabel()
@pytest.mark.parametrize('n_jobs', [
    1,
    pytest.param(2, marks=pytest.mark.slowtest),  # 1.5 sec locally
])
@pytest.mark.filterwarnings('ignore:No contour levels were.*:UserWarning')
def test_add_bem_n_jobs(n_jobs, monkeypatch):
    """Test add_bem with n_jobs."""
    if n_jobs == 1:  # in one case, do at init -- in the other, pass in
        use_subjects_dir = None
    else:
        use_subjects_dir = subjects_dir
    report = Report(subjects_dir=use_subjects_dir)
    # implicitly test that subjects_dir is correctly preserved here
    monkeypatch.setattr(report_mod, '_BEM_VIEWS', ('axial',))
    if use_subjects_dir is not None:
        use_subjects_dir = None
    report.add_bem(
        subject='sample', title='sample', tags=('sample',), decim=15,
        n_jobs=n_jobs, subjects_dir=subjects_dir
    )
    assert len(report.html) == 1
    imgs = np.array([plt.imread(BytesIO(base64.b64decode(b)), 'png')
                     for b in re.findall(r'data:image/png;base64,(\S*)">',
                                         report.html[0])])
    assert imgs.ndim == 4  # images, h, w, rgba
    assert len(imgs) == 6
    imgs.shape = (len(imgs), -1)
    norms = np.linalg.norm(imgs, axis=-1)
    # should have down-up-down shape
    corr = np.corrcoef(norms, np.hanning(len(imgs)))[0, 1]
    assert 0.778 < corr < 0.80


@testing.requires_testing_data
@requires_nibabel()
def test_render_mri_without_bem(tmp_path):
    """Test rendering MRI without BEM for mne report."""
    tempdir = str(tmp_path)
    os.mkdir(op.join(tempdir, 'sample'))
    os.mkdir(op.join(tempdir, 'sample', 'mri'))
    shutil.copyfile(mri_fname, op.join(tempdir, 'sample', 'mri', 'T1.mgz'))
    report = Report(info_fname=raw_fname,
                    subject='sample', subjects_dir=tempdir)
    with pytest.raises(RuntimeError, match='No matching files found'):
        report.parse_folder(tempdir, render_bem=False)
    with pytest.warns(RuntimeWarning, match='No BEM surfaces found'):
        report.parse_folder(tempdir, render_bem=True, mri_decim=20)
    assert 'BEM surfaces' in [element.name for element in report._content]
    report.save(op.join(tempdir, 'report.html'), open_browser=False)


@testing.requires_testing_data
@requires_nibabel()
def test_add_html():
    """Test adding html str to mne report."""
    report = Report(info_fname=raw_fname,
                    subject='sample', subjects_dir=subjects_dir)
    html = '<b>MNE-Python is AWESOME</b>'
    report.add_html(html=html, title='html')
    assert (html in report.html[0])
    assert (repr(report))


@testing.requires_testing_data
def test_multiple_figs(tmp_path):
    """Test adding a slider with a series of figures to a Report."""
    tempdir = str(tmp_path)
    report = Report(info_fname=raw_fname,
                    subject='sample', subjects_dir=subjects_dir)
    figs = _get_example_figures()
    report.add_figure(fig=figs, title='my title')
    assert report._content[0].name == 'my title'
    report.save(op.join(tempdir, 'report.html'), open_browser=False)

    with pytest.raises(ValueError):
        report.add_figure(fig=figs, title='title', caption=['wug'])

    with pytest.raises(ValueError,
                       match='Number of captions.*must be equal to.*figures'):
        report.add_figure(fig=figs, title='title', caption='wug')

    # Smoke test that SVG with unicode can be added
    report = Report()
    fig, ax = plt.subplots()
    ax.set_xlabel('µ')
    report.add_figure(fig=[fig] * 2, title='title', image_format='svg')


def test_validate_input():
    """Test Report input validation."""
    report = Report()
    items = ['a', 'b', 'c']
    captions = ['Letter A', 'Letter B', 'Letter C']
    section = 'ABCs'
    comments = ['First letter of the alphabet.',
                'Second letter of the alphabet',
                'Third letter of the alphabet']
    pytest.raises(ValueError, report._validate_input, items, captions[:-1],
                  section, comments=None)
    pytest.raises(ValueError, report._validate_input, items, captions, section,
                  comments=comments[:-1])
    values = report._validate_input(items, captions, section, comments=None)
    items_new, captions_new, comments_new = values


@requires_h5py
def test_open_report(tmp_path):
    """Test the open_report function."""
    tempdir = str(tmp_path)
    hdf5 = op.join(tempdir, 'report.h5')

    # Test creating a new report through the open_report function
    fig1 = _get_example_figures()[0]
    with open_report(hdf5, subjects_dir=subjects_dir) as report:
        assert report.subjects_dir == subjects_dir
        assert report.fname == hdf5
        report.add_figure(fig=fig1, title='evoked response')
    # Exiting the context block should have triggered saving to HDF5
    assert op.exists(hdf5)

    # Load the HDF5 version of the report and check equivalence
    report2 = open_report(hdf5)
    assert report2.fname == hdf5
    assert report2.subjects_dir == report.subjects_dir
    assert report2.html == report.html
    assert report2.__getstate__() == report.__getstate__()
    assert '_fname' not in report2.__getstate__()

    # Check parameters when loading a report
    pytest.raises(ValueError, open_report, hdf5, foo='bar')  # non-existing
    pytest.raises(ValueError, open_report, hdf5, subjects_dir='foo')
    open_report(hdf5, subjects_dir=subjects_dir)  # This should work

    # Check that the context manager doesn't swallow exceptions
    with pytest.raises(ZeroDivisionError):
        with open_report(hdf5, subjects_dir=subjects_dir) as report:
            1 / 0


def test_remove():
    """Test removing figures from a report."""
    r = Report()
    fig1, fig2 = _get_example_figures()
    r.add_figure(fig=fig1, title='figure1', tags=('slider',))
    r.add_figure(fig=[fig1, fig2], title='figure1', tags=('othertag',))
    r.add_figure(fig=fig2, title='figure1', tags=('slider',))
    r.add_figure(fig=fig2, title='figure2', tags=('slider',))

    # Test removal by title
    r2 = copy.deepcopy(r)
    removed_index = r2.remove(title='figure1')
    assert removed_index == 2
    assert len(r2.html) == 3
    assert r2.html[0] == r.html[0]
    assert r2.html[1] == r.html[1]
    assert r2.html[2] == r.html[3]

    # Test restricting to section
    r2 = copy.deepcopy(r)
    removed_index = r2.remove(title='figure1', tags=('othertag',))
    assert removed_index == 1
    assert len(r2.html) == 3
    assert r2.html[0] == r.html[0]
    assert r2.html[1] == r.html[2]
    assert r2.html[2] == r.html[3]


def test_add_or_replace():
    """Test replacing existing figures in a report."""
    r = Report()
    fig1, fig2 = _get_example_figures()
    r.add_figure(fig=fig1, title='duplicate', tags=('foo',))
    r.add_figure(fig=fig1, title='duplicate', tags=('foo',))
    r.add_figure(fig=fig1, title='duplicate', tags=('bar',))
    r.add_figure(fig=fig2, title='nonduplicate', tags=('foo',))
    # By default, replace=False, so all figures should be there
    assert len(r.html) == 4

    old_r = copy.deepcopy(r)

    # Replace last occurrence of `fig1` tagges as `foo`
    r.add_figure(
        fig=fig2, title='duplicate', tags=('foo',), replace=True
    )
    assert len(r._content) == len(r.html) == 4
    assert r.html[1] != old_r.html[1]  # This figure should have changed
    # All other figures should be the same
    assert r.html[0] == old_r.html[0]
    assert r.html[2] == old_r.html[2]
    assert r.html[3] == old_r.html[3]


def test_scraper(tmp_path):
    """Test report scraping."""
    r = Report()
    fig1, fig2 = _get_example_figures()
    r.add_figure(fig=fig1, title='a')
    r.add_figure(fig=fig2, title='b')
    # Mock a Sphinx + sphinx_gallery config
    app = Bunch(builder=Bunch(srcdir=str(tmp_path),
                              outdir=op.join(str(tmp_path), '_build', 'html')))
    scraper = _ReportScraper()
    scraper.app = app
    gallery_conf = dict(src_dir=app.builder.srcdir, builder_name='html')
    img_fname = op.join(app.builder.srcdir, 'auto_examples', 'images',
                        'sg_img.png')
    target_file = op.join(app.builder.srcdir, 'auto_examples', 'sg.py')
    os.makedirs(op.dirname(img_fname))
    os.makedirs(app.builder.outdir)
    block_vars = dict(image_path_iterator=(img for img in [img_fname]),
                      example_globals=dict(a=1), target_file=target_file)
    # Nothing yet
    block = None
    rst = scraper(block, block_vars, gallery_conf)
    assert rst == ''
    # Still nothing
    block_vars['example_globals']['r'] = r
    rst = scraper(block, block_vars, gallery_conf)
    # Once it's saved, add it
    assert rst == ''
    fname = op.join(str(tmp_path), 'my_html.html')
    r.save(fname, open_browser=False)
    rst = scraper(block, block_vars, gallery_conf)
    out_html = op.join(app.builder.outdir, 'auto_examples', 'my_html.html')
    assert not op.isfile(out_html)
    scraper.copyfiles()
    assert op.isfile(out_html)
    assert rst.count('"') == 6
    assert "<iframe" in rst
    assert op.isfile(img_fname.replace('png', 'svg'))


@testing.requires_testing_data
@pytest.mark.parametrize('split_naming', ('neuromag', 'bids',))
def test_split_files(tmp_path, split_naming):
    """Test that in the case of split files, we only parse the first."""
    raw = read_raw_fif(raw_fname)
    split_size = '7MB'  # Should produce 3 files
    buffer_size_sec = 1  # Tiny buffer so it's smaller than the split size
    raw.save(op.join(tmp_path, 'raw_meg.fif'), split_size=split_size,
             split_naming=split_naming, buffer_size_sec=buffer_size_sec)

    report = Report()
    report.parse_folder(tmp_path, render_bem=False, raw_butterfly=False)
    assert len(report._content) == 1


@pytest.mark.slowtest  # ~40 sec on Azure Windows
@testing.requires_testing_data
def test_survive_pickle(tmp_path):
    """Testing functionality of Report-Object after pickling."""
    tempdir = str(tmp_path)
    raw_fname_new = op.join(tempdir, 'temp_raw.fif')
    shutil.copyfile(raw_fname, raw_fname_new)

    # Pickle report object to simulate multiprocessing with joblib
    report = Report(info_fname=raw_fname_new)
    pickled_report = pickle.dumps(report)
    report = pickle.loads(pickled_report)

    # Just test if no errors occur
    report.parse_folder(tempdir, render_bem=False)
    save_name = op.join(tempdir, 'report.html')
    report.save(fname=save_name, open_browser=False)


@pytest.mark.slowtest  # ~30 sec on Azure Windows
@requires_sklearn
@testing.requires_testing_data
def test_manual_report_2d(tmp_path, invisible_fig):
    """Simulate user manually creating report by adding one file at a time."""
    from sklearn.exceptions import ConvergenceWarning

    r = Report(title='My Report')
    raw = read_raw_fif(raw_fname)
    raw.pick_channels(raw.ch_names[:6]).crop(10, None)
    raw.info.normalize_proj()
    cov = read_cov(cov_fname)
    cov = pick_channels_cov(cov, raw.ch_names)
    events = read_events(events_fname)
    epochs = Epochs(raw=raw, events=events, baseline=None)
    evokeds = read_evokeds(evoked_fname)
    evoked = evokeds[0].pick('eeg')

    with pytest.warns(ConvergenceWarning, match='did not converge'):
        ica = (ICA(n_components=2, max_iter=1, random_state=42)
               .fit(inst=raw.copy().crop(tmax=1)))
    ica_ecg_scores = ica_eog_scores = np.array([3, 0])
    ica_ecg_evoked = ica_eog_evoked = epochs.average()

    r.add_raw(raw=raw, title='my raw data', tags=('raw',), psd=True,
              projs=False)
    r.add_events(events=events_fname, title='my events',
                 sfreq=raw.info['sfreq'])
    r.add_epochs(epochs=epochs, title='my epochs', tags=('epochs',), psd=False,
                 projs=False)
    r.add_evokeds(evokeds=evoked, noise_cov=cov_fname,
                  titles=['my evoked 1'], tags=('evoked',), projs=False,
                  n_time_points=2)
    r.add_projs(info=raw_fname, projs=ecg_proj_fname, title='my proj',
                tags=('ssp', 'ecg'))
    r.add_ica(ica=ica, title='my ica', inst=None)
    with pytest.raises(RuntimeError, match='not preloaded'):
        r.add_ica(ica=ica, title='ica', inst=raw)
    r.add_ica(
        ica=ica, title='my ica with inst',
        inst=raw.copy().load_data(),
        picks=[0],
        ecg_evoked=ica_ecg_evoked,
        eog_evoked=ica_eog_evoked,
        ecg_scores=ica_ecg_scores,
        eog_scores=ica_eog_scores
    )
    r.add_covariance(cov=cov, info=raw_fname, title='my cov')
    r.add_forward(forward=fwd_fname, title='my forward', subject='sample',
                  subjects_dir=subjects_dir)
    r.add_html(html='<strong>Hello</strong>', title='Bold')
    r.add_code(code=__file__, title='my code')
    r.add_sys_info(title='my sysinfo')

    # drop locations (only EEG channels in `evoked`)
    evoked_no_ch_locs = evoked.copy()
    for ch in evoked_no_ch_locs.info['chs']:
        ch['loc'][:3] = np.nan

    with pytest.warns(RuntimeWarning, match='No EEG channel locations'):
        r.add_evokeds(
            evokeds=evoked_no_ch_locs, titles=['evoked no chan locs'],
            tags=('evoked',), projs=True, n_time_points=1
        )
    assert 'Time course' not in r._content[-1].html
    assert 'Topographies' not in r._content[-1].html
    assert evoked.info['projs']  # only then the following test makes sense
    assert 'SSP' not in r._content[-1].html
    assert 'Global field power' in r._content[-1].html

    # Drop locations from Info used for projs
    info_no_ch_locs = raw.info.copy()
    for ch in info_no_ch_locs['chs']:
        ch['loc'][:3] = np.nan

    with pytest.warns(RuntimeWarning, match='No channel locations found'):
        r.add_projs(info=info_no_ch_locs, title='Projs no chan locs')

    # Drop locations from ICA
    ica_no_ch_locs = ica.copy()
    for ch in ica_no_ch_locs.info['chs']:
        ch['loc'][:3] = np.nan

    with pytest.warns(
        RuntimeWarning,
        match='No Magnetometers channel locations'
    ):
        r.add_ica(
            ica=ica_no_ch_locs, picks=[0],
            inst=raw.copy().load_data(), title='ICA'
        )
    assert 'ICA component properties' not in r._content[-1].html
    assert 'ICA component topographies' not in r._content[-1].html
    assert 'Original and cleaned signal' in r._content[-1].html

    fname = op.join(tmp_path, 'report.html')
    r.save(fname=fname, open_browser=False)


@pytest.mark.slowtest  # 30 sec on Azure for Mayavi
@testing.requires_testing_data
def test_manual_report_3d(tmp_path, renderer):
    """Simulate adding 3D sections."""
    r = Report(title='My Report')
    r.add_trans(trans=trans_fname, info=raw_fname, title='my coreg',
                subject='sample', subjects_dir=subjects_dir)
    r.add_bem(subject='sample', subjects_dir=subjects_dir, title='my bem',
              decim=100)
    r.add_inverse_operator(
        inverse_operator=inv_fname, title='my inverse', subject='sample',
        subjects_dir=subjects_dir, trans=trans_fname
    )
    r.add_stc(
        stc=stc_fname, title='my stc', subject='sample',
        subjects_dir=subjects_dir, n_time_points=2,
        stc_plot_kwargs=stc_plot_kwargs,
    )
    fname = op.join(tmp_path, 'report.html')
    r.save(fname=fname, open_browser=False)


def test_sorting(tmp_path):
    """Test that automated ordering based on tags works."""
    r = Report()

    r.add_code(code='E = m * c**2', title='intelligence >9000', tags=('bem',))
    r.add_code(code='a**2 + b**2 = c**2', title='Pythagoras', tags=('evoked',))
    r.add_code(code='🧠', title='source of truth', tags=('source-estimate',))
    r.add_code(code='🥦', title='veggies', tags=('raw',))

    # Check that repeated calls of add_* actually continuously appended to
    # the report
    orig_order = ['bem', 'evoked', 'source-estimate', 'raw']
    assert [c.tags[0] for c in r._content] == orig_order

    # Now check the actual sorting
    content_sorted = r._sort(content=r._content, order=CONTENT_ORDER)
    expected_order = ['raw', 'evoked', 'bem', 'source-estimate']

    assert content_sorted != r._content
    assert [c.tags[0] for c in content_sorted] == expected_order

    r.save(fname=op.join(tmp_path, 'report.html'), sort_content=True,
           open_browser=False)


@testing.requires_testing_data
def test_deprecated_methods(tmp_path):
    """Test methods that are scheduled for removal after 0.24."""
    r = Report()
    r.add_projs(info=raw_fname, title='SSP Projectors', tags=('mytag',))
    fig = plt.figure()  # Empty figure
    img_fname = op.join(tmp_path, 'testimage.png')
    fig.savefig(img_fname)

    with pytest.warns(DeprecationWarning, match='Report.fnames'):
        assert len(r.fnames) == 1

    with pytest.warns(DeprecationWarning, match='Report.sections'):
        assert len(r.sections) == 1

    with pytest.warns(DeprecationWarning, match='use "title" instead'):
        r.remove(caption='SSP Projectors')

    with pytest.warns(DeprecationWarning, match='use .* instead'):
        r.remove(caption='SSP Projectors', tags=('mytag',))

    with pytest.warns(DeprecationWarning, match='Use.*Report.add_figure'):
        with pytest.raises(TypeError, match='It seems you passed a path'):
            r.add_figs_to_section(['foo'], 'caption', 'section')

    with pytest.raises(
        ValueError,
        match='Number of "captions" and report items must be equal'
    ):
        with pytest.warns(DeprecationWarning, match='Use.*Report.add_figure'):
            r.add_figs_to_section(figs=[fig, fig], captions='H')

    # Passing lists should work
    with pytest.warns(DeprecationWarning, match='Use.*Report.add_image'):
        r.add_images_to_section(fnames=[img_fname],
                                captions=['evoked response'])

    with pytest.raises(
        ValueError,
        match='Number of "captions" and report items must be equal'
    ):
        with pytest.warns(DeprecationWarning, match='Use.*Report.add_image'):
            r.add_images_to_section(fnames=[img_fname, img_fname],
                                    captions='H')

    with pytest.warns(DeprecationWarning, match='Use.*Report.add_bem'):
        r.add_bem_to_section(
            subject='sample', subjects_dir=subjects_dir, decim=100
        )


@pytest.mark.parametrize(
    ('tags', 'not_a_collection', 'wrong_dtype', 'invalid_chars'),
    [
        # not a collection
        ('foo', True, False, False),
        (123, True, False, False),
        # wrong dtype
        ([1, 2, 3], False, True, False),
        (['foo', 1], False, True, False),
        # invalid characters
        (['foo bar'], False, False, True),
        (['foo"'], False, False, True),
        (['foo\n'], False, False, True),
        # all good
        (['foo'], False, False, False),
        (['foo', 'bar'], False, False, False),
        (np.array(['foo', 'bar']), False, False, False)
    ]
)
def test_tags(tags, not_a_collection, wrong_dtype, invalid_chars):
    """Test handling of invalid tags."""
    r = Report()

    if not_a_collection:
        with pytest.raises(TypeError, match='must be a collection of str'):
            r.add_code(code='foo', title='bar', tags=tags)
    elif wrong_dtype:
        with pytest.raises(TypeError, match='must be strings'):
            r.add_code(code='foo', title='bar', tags=tags)
    elif invalid_chars:
        with pytest.raises(ValueError, match='contained invalid characters'):
            r.add_code(code='foo', title='bar', tags=tags)
    else:
        r.add_code(code='foo', title='bar', tags=tags)
