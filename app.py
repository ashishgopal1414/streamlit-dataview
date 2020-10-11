from matplotlib.backends.backend_agg import RendererAgg
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

import requests
import os
from gwpy.timeseries import TimeSeries
from gwosc.locate import get_urls
from gwosc import datasets
from gwosc.api import fetch_event_json

from copy import deepcopy
import base64

# Use the non-interactive Agg backend, which is recommended as a
# thread-safe backend.
# See https://matplotlib.org/3.3.2/faq/howto_faq.html#working-with-threads.
import matplotlib as mpl
mpl.use("agg")

##############################################################################
# Workaround for the limited multi-threading support in matplotlib.
# Per the docs, we will avoid using `matplotlib.pyplot` for figures:
# https://matplotlib.org/3.3.2/faq/howto_faq.html#how-to-use-matplotlib-in-a-web-application-server.
# Moreover, we will guard all operations on the figure instances by the
# class-level lock in the Agg backend.
##############################################################################
_lock = RendererAgg.lock

# -- Default detector list
detectorlist = ['H1', 'L1', 'V1']

# Title the app
st.title('Gravitational Wave Quickview App')

st.markdown("""
 * Use the menu at left to select data and set plot parameters
 * Your plots will appear below
""")


@st.cache  # -- Magic command to cache data
def load_gw(t0, detector):
    strain = TimeSeries.fetch_open_data(detector, t0-14, t0+14, cache=False)
    return strain


@st.cache
def get_eventslist():
    # -- Get list of events
    # find_datasets(catalog='GWTC-1-confident',type='events')
    eventlist = datasets.find_datasets(type='events')
    eventlist = [name.split('-')[0] for name in eventlist if name[0:2] == 'GW']
    eventset = set([name for name in eventlist])
    eventlist = list(eventset)
    eventlist.sort()
    return eventlist


@st.cache
def get_detectorlist(chosen_event):
    t0 = datasets.event_gps(chosen_event)
    detectorlist = list(datasets.event_detectors(chosen_event))
    detectorlist.sort()
    jsoninfo = fetch_event_json(chosen_event)

    return t0, detectorlist, jsoninfo


st.sidebar.markdown("## Select Data Time and Detector")

eventlist = get_eventslist()

# -- Set time by GPS or event
select_event = st.sidebar.selectbox('How do you want to find data?',
                                    ['By event name', 'By GPS'])

if select_event == 'By GPS':
    # -- Set a GPS time:
    str_t0 = st.sidebar.text_input('GPS Time', '1126259462.4')    # -- GW150914
    t0 = float(str_t0)

    st.sidebar.markdown("""
    Example times in the H1 detector:
    * 1126259462.4    (GW150914) 
    * 1187008882.4    (GW170817) 
    * 933200215       (hardware injection)
    * 1132401286.33   (Koi Fish Glitch) 
    """)

else:
    chosen_event = st.sidebar.selectbox('Select Event', eventlist)
    st.subheader(chosen_event)

    # -- Experiment to display masses
    try:
        t0, detectorlist, jsoninfo = get_detectorlist(chosen_event)
        for name, nameinfo in jsoninfo['events'].items():
            st.write('Mass 1:', nameinfo['mass_1_source'], 'M$_{\odot}$')
            st.write('Mass 2:', nameinfo['mass_2_source'], 'M$_{\odot}$')
            #st.write('Distance:', int(nameinfo['luminosity_distance']), 'Mpc')
            st.write('Network SNR:', int(
                nameinfo['network_matched_filter_snr']))
            eventurl = 'https://gw-osc.org/eventapi/html/event/{}'.format(
                chosen_event)
            st.markdown('Event page: {}'.format(eventurl))
            st.write('\n')
    except:
        pass


# -- Choose detector as H1, L1, or V1
detector = st.sidebar.selectbox('Detector', detectorlist)

# -- Create sidebar for plot controls
st.sidebar.markdown('## Set Plot Parameters')
dtboth = st.sidebar.slider('Time Range (seconds)',
                           0.1, 8.0, 1.0)  # min, max, default
dt = dtboth / 2.0

st.sidebar.markdown('#### Whitened and band-passed data')
whiten = st.sidebar.checkbox('Whiten?', value=True)
freqrange = st.sidebar.slider(
    'Band-pass frequency range (Hz)', min_value=10, max_value=2000, value=(30, 400))


# -- Create sidebar for Q-transform controls
st.sidebar.markdown('#### Q-tranform plot')
vmax = st.sidebar.slider('Colorbar Max Energy', 10,
                         500, 25)  # min, max, default
qcenter = st.sidebar.slider('Q-value', 5, 120, 5)  # min, max, default
qrange = (int(qcenter*0.8), int(qcenter*1.2))


# -- Create a text element and let the reader know the data is loading.
strain_load_state = st.text('Loading data...this may take a minute')
try:
    strain_data = load_gw(t0, detector)
except:
    st.text('Data load failed.  Try a different time and detector pair.')
    st.text('Problems can be reported to gwosc@igwn.org')
    st.stop()

strain_load_state.text('Loading data...done!')

# -- Make a time series plot

cropstart = t0-0.2
cropend = t0+0.1

cropstart = t0 - dt
cropend = t0 + dt

st.subheader('Raw data')
center = int(t0)
strain = deepcopy(strain_data)
with _lock:
    fig1 = strain.crop(cropstart, cropend).plot()
    st.pyplot(fig1, clear_figure=True)


# -- Try whitened and band-passed plot
# -- Whiten and bandpass data
st.subheader('Whitened and Band-passed Data')

if whiten:
    white_data = strain.whiten()
    bp_data = white_data.bandpass(freqrange[0], freqrange[1])
else:
    bp_data = strain.bandpass(freqrange[0], freqrange[1])

bp_cropped = bp_data.crop(cropstart, cropend)
with _lock:
    fig3 = bp_cropped.plot()
    st.pyplot(fig3, clear_figure=True)

# -- Allow data download


@st.cache
def create_download_data(bp_cropped):
    download = {'Time': bp_cropped.times, 'Strain': bp_cropped.value}
    df = pd.DataFrame(download)
    csv = df.to_csv(index=False)
    # some strings <-> bytes conversions necessary here
    return base64.b64encode(csv.encode()).decode()


b64 = create_download_data(bp_cropped)
href = f'<a href="data:file/csv;base64,{b64}">Download Data as CSV File</a>'
st.markdown(href, unsafe_allow_html=True)


@st.cache
def qtransform(t0, dt, qrange):
    return strain.q_transform(outseg=(t0-dt, t0+dt), qrange=qrange)


st.subheader('Q-transform')
hq = qtransform(t0, dt, qrange)

with _lock:
    fig4 = hq.plot()
    ax = fig4.gca()
    fig4.colorbar(label="Normalised energy", vmax=vmax, vmin=0)
    ax.grid(False)
    ax.set_yscale('log')
    ax.set_ylim(bottom=15)
    st.pyplot(fig4, clear_figure=True)


st.subheader("About this app")
st.markdown("""
This app displays data from LIGO, Virgo, and GEO downloaded from
the Gravitational Wave Open Science Center at https://gw-openscience.org .


You can see how this works in the [Quickview Jupyter Notebook](https://github.com/losc-tutorial/quickview)

""")
