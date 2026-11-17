'use strict';

const PREFIX = '[report]';

function log(...a) {
  console.log(PREFIX, ...a);
}

function error(...a) {
  console.error(PREFIX, ...a);
}

module.exports = { log, error };
