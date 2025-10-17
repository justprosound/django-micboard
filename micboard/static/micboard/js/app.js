"use strict";

import QRCode from 'qrcode';
import 'whatwg-fetch';

import { autoRandom, seedTransmitters } from './demodata.js';
import { renderGroup, renderDisplayList, updateSlot } from './channelview.js';
import { initLiveData } from './data.js';
import { groupEditToggle, initEditor } from './dnd.js';
import { slotEditToggle } from './extended.js';
import { keybindings } from './kbd.js';
import { setBackground, setInfoDrawer } from './display.js';
import { setTimeMode } from './chart-smoothie.js';
import { initConfigEditor } from './config.js';

import '../css/colors.scss';
import '../css/style.scss';


export const dataURL = window.dataURL || 'data.json';

export const micboard = [];
micboard.MIC_MODELS = ['uhfr', 'qlxd', 'ulxd', 'axtd'];
micboard.IEM_MODELS = ['p10t'];
micboard.url = [];
micboard.displayMode = 'deskmode';
micboard.infoDrawerMode = 'elinfo11';
micboard.backgroundMode = 'NONE';
micboard.settingsMode = 'NONE';
micboard.chartTimeSrc = 'SERVER';

micboard.group = 0;
micboard.connectionStatus = 'CONNECTING';

// micboard.transmitters = []; // Removed
micboard.receivers = []; // Added to hold the new data structure

micboard.displayList = [];

export function ActivateMessageBoard(h1, p) {
  if (!h1) {
    h1 = 'Connection Error!';
    p = 'Could not connect to the micboard server. Please <a href=".">refresh</a> the page.';
  }

  document.getElementById('micboard').style.display = 'none';
  document.querySelector('.settings').style.display = 'none';
  const eb = document.getElementsByClassName('message-board')[0];
  eb.querySelector('h1').innerHTML = h1;
  eb.querySelector('p').innerHTML = p;

  document.querySelector('.message-board').style.display = 'block';

  micboard.connectionStatus = 'DISCONNECTED';
}

export function generateQR() {
  const qrOptions = {
    width: 600,
    margin: 0,
  };

  const url = micboard.localURL + location.pathname + location.search;
  document.getElementById('largelink').href = url;
  document.getElementById('largelink').innerHTML = url;
  QRCode.toCanvas(document.getElementById('qrcode'), url, qrOptions, (error) => {
    if (error) console.error(error)
    console.log('success!');
  });

  document.getElementById('micboard-version').innerHTML = 'Micboard version: ' + VERSION;
}

function groupTableBuilder(data) {
  const plist = {};

  // Assuming data.groups is still available and structured similarly
  data.groups.forEach((e) => {
    const entry = {
      slots: e.slots, // This will need to be re-evaluated later
      title: e.title,
      hide_charts: e.hide_charts,
    };

    if (entry.hide_charts == null) {
      entry.hide_charts = false;
    }

    plist[e.group] = entry;
  });

  return plist;
}

export function updateNavLinks() {
  let str = '';
  for (let i = 1; i <= 9; i += 1) {
    str = '';
    if (micboard.groups[i]) {
      str = `${i}: ${micboard.groups[i].title}`;
    } else {
      str = `${i}:`;
    }
    document.getElementById(`go-group-${i}`).innerHTML = str;
  }
}

function mapGroups() {
  document.getElementById('go-extended').addEventListener('click', () => {
            document.querySelectorAll('.collapse').forEach(el => el.style.display = 'none');  });

  document.getElementById('go-config').addEventListener('click', () => {
    document.querySelectorAll('.collapse').forEach(el => el.style.display = 'none');
  });

  document.getElementById('go-groupedit').addEventListener('click', () => {
    if (micboard.group !== 0) {
    document.querySelectorAll('.collapse').forEach(el => el.style.display = 'none');
    }
  });

  document.querySelectorAll('a.preset-link').forEach((element) => {
    const id = parseInt(element.id[9], 10);

    element.addEventListener('click', () => {
      renderGroup(id);
      document.querySelectorAll('.collapse').forEach(el => el.style.display = 'none');
    });
  });

  updateNavLinks();
}

// https://stackoverflow.com/questions/19491336/get-url-parameter-jquery-or-how-to-get-query-string-values-in-js
// var getUrlParameter = function getUrlParameter(sParam) {
function getUrlParameter(sParam) {
  // const sPageURL = decodeURIComponent(window.location.search.substring(1));
  const sPageURL = decodeURIComponent(window.location.hash.substring(1));
  const sURLVariables = sPageURL.split('&');
  let sParameterName;
  let i;

  for (i = 0; i < sURLVariables.length; i += 1) {
    sParameterName = sURLVariables[i].split('=');

    if (sParameterName[0] === sParam) {
      return sParameterName[1] === undefined ? true : sParameterName[1];
    }
  }
  return undefined;
}


function readURLParameters() {
  micboard.url.group = getUrlParameter('group');
  micboard.url.demo = getUrlParameter('demo');
  micboard.url.settings = getUrlParameter('settings');
  micboard.url.tvmode = getUrlParameter('tvmode');
  micboard.url.bgmode = getUrlParameter('bgmode');

  if (window.location.pathname.includes('demo')) {
    micboard.url.demo = 'true';
  }
}

export function updateHash() {
  let hash = '#';
  if (micboard.url.demo) {
    hash += '&demo=true';
  }
  if (micboard.group !== 0) {
    hash += '&group=' + micboard.group;
  }
  if (micboard.displayMode === 'tvmode') {
    hash += '&tvmode=' + micboard.infoDrawerMode;
  }
  if (micboard.backgroundMode !== 'NONE') {
    hash += '&bgmode=' + micboard.backgroundMode;
  }
  if (micboard.settingsMode === 'CONFIG') {
    hash = '#settings=true'
  }
  hash = hash.replace('&', '');
  history.replaceState(undefined, undefined, hash);

}

// Removed dataFilterFromList as it's no longer relevant with the new data structure
// function dataFilterFromList(data) {
//   data.receivers.forEach((rx) => {
//     rx.tx.forEach((t) => {
//       const tx = t;
//       tx.ip = rx.ip;
//       tx.type = rx.type;
//       micboard.transmitters[tx.slot] = tx;
//     });
//   });
// }

function displayListChooser() {
  if (micboard.url.group) {
    renderGroup(micboard.url.group);
  } else {
    renderGroup(0);
  }
}



function initialMap(callback) {
  fetch(dataURL)
    .then((response) => {
      setTimeMode(response.headers.get('Date'));

      response.json().then((data) => {
        micboard.discovered = data.discovered;
        micboard.mp4_list = data.mp4;
        micboard.img_list = data.jpg;
        micboard.localURL = data.url;
        micboard.groups = groupTableBuilder(data);
        micboard.config = data.config;

        // Store the new receivers data structure
        micboard.receivers = data.receivers; // Updated

        // Rebuild legacy transmitters mapping expected by other modules.
        // Some parts of the frontend still expect `micboard.transmitters`.
        micboard.transmitters = [];
        if (Array.isArray(micboard.receivers)) {
          micboard.receivers.forEach((rx) => {
            if (!rx || !Array.isArray(rx.tx)) return;
            rx.tx.forEach((t) => {
              const tx = t;
              // carry over some receiver properties to transmitter for compatibility
              tx.ip = rx.ip;
              tx.type = rx.type;
              micboard.transmitters[tx.slot] = tx;
            });
          });
        }

        mapGroups();

        if (micboard.config.slots.length < 1) {
          setTimeout(function() {
            initConfigEditor();
          }, 125);
        }

        // No longer need dataFilterFromList
        // if (micboard.url.demo !== 'true') {
        //   dataFilterFromList(data);
        // }
        displayListChooser();

        if (callback) {
          callback();
        }
        if (['MP4', 'IMG'].indexOf(micboard.url.bgmode) >= 0) {
          setBackground(micboard.url.bgmode);
        }
        if (['elinfo00', 'elinfo01', 'elinfo10', 'elinfo11'].indexOf(micboard.url.tvmode) >= 0) {
          setInfoDrawer(micboard.url.tvmode);
        }
        initEditor();
      });
    });
}


document.addEventListener('DOMContentLoaded', () => {
  console.log('Starting Micboard version: ' + VERSION);
  readURLParameters();
  keybindings();
  if (micboard.url.demo === 'true') {
    setTimeout(() => {
      document.getElementById('hud').style.display = 'block';
    }, 100);

    initialMap();
  } else {
    initialMap(initLiveData);
  }

  if (micboard.url.settings === 'true') {
    setTimeout(() => {
      initConfigEditor();
      updateHash();
    }, 100);
  }
});
