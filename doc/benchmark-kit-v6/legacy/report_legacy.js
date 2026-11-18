'use strict';

const { log } = require('./logger');

function formatTimestamp(ms) {
  const d = new Date(ms);
  const p = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} `
    + `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function renderRow(r) {
  return [formatTimestamp(r.ts), r.level, r.msg].join(' ');
}

module.exports = { formatTimestamp, renderRow };
