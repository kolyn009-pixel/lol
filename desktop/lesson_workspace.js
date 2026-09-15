'use strict';
const { app, BrowserWindow, Notification } = require('electron');

const APP_ORIGIN = 'https://adeliatutor.ru';
const POLL_MS = 60 * 1000;
const REMINDER_MINUTES = [15, 5];
let timer = null;
let lastLesson = null;
let notificationsEnabled = true;
const sent = new Set();

function isStudentCabinetUrl(raw) {
  try {
    const u = new URL(raw);
    if (u.origin !== APP_ORIGIN) return false;
    if (!u.pathname.startsWith('/app/')) return false;
    if (u.pathname.startsWith('/app/parent/')) return false;
    return true;
  } catch (_) { return false; }
}
function mainWindow() {
  return BrowserWindow.getAllWindows().find(w => !w.isDestroyed() && isStudentCabinetUrl(w.webContents.getURL())) || null;
}
function lessonTarget(id) {
  const u = new URL('/app/', APP_ORIGIN);
  u.searchParams.set('desktop', 'lesson');
  if (id != null) u.searchParams.set('id', String(id));
  return u.toString();
}
function showLesson(id) {
  const win = mainWindow();
  if (!win) return;
  if (win.isMinimized()) win.restore();
  win.show();
  win.focus();
  win.loadURL(lessonTarget(id));
}
function normalizeLesson(raw) {
  if (!raw || !raw.start_time) return null;
  const start = new Date(raw.start_time);
  if (Number.isNaN(start.getTime())) return null;
  return {
    id: raw.id,
    subject: String(raw.subject || 'Занятие'),
    start,
    duration: Number(raw.duration_minutes || 60),
    started: !!raw.started_at,
  };
}
function subjectName(value) {
  return ({ PHYSICS: 'Физика', CHEMISTRY: 'Химия' })[String(value || '').toUpperCase()] || value || 'Занятие';
}
function formatTime(date) {
  return new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit' }).format(date);
}
function publicLesson(lesson) {
  return lesson ? {
    id: lesson.id,
    subject: subjectName(lesson.subject),
    start_time: lesson.start.toISOString(),
    duration_minutes: lesson.duration,
    started: lesson.started,
  } : null;
}
function notificationKey(lesson, minutes) { return `${lesson.id}:${minutes}`; }
function notifyLesson(lesson, minutes) {
  if (!notificationsEnabled || !Notification.isSupported()) return;
  const key = notificationKey(lesson, minutes);
  if (sent.has(key)) return;
  sent.add(key);
  const title = minutes <= 0 ? '💜 Занятие начинается' : `💜 Через ${minutes} минут занятие`;
  const body = `${subjectName(lesson.subject)} · ${formatTime(lesson.start)}\nНажмите, чтобы открыть Аделию.`;
  const n = new Notification({ title, body, silent: false, timeoutType: 'default' });
  n.on('click', () => showLesson(lesson.id));
  n.show();
}
async function readDashboard() {
  const win = mainWindow();
  if (!win || win.isDestroyed()) return null;
  const url = win.webContents.getURL();
  if (!isStudentCabinetUrl(url)) return null;
  try {
    return await win.webContents.executeJavaScript(`fetch('/api/student/dashboard',{credentials:'same-origin',cache:'no-store'}).then(async r=>r.ok?await r.json():null).catch(()=>null)`, true);
  } catch (_) { return null; }
}
async function poll() {
  const data = await readDashboard();
  if (!data) {
    lastLesson = null;
    return;
  }
  const lesson = normalizeLesson(data.next_lesson);
  lastLesson = lesson;
  app.emit('adelia-dashboard-state', {
    nextLesson: publicLesson(lesson),
    unreadMessages: Math.max(0, Number(data.unread_messages || 0)),
    activeHomework: Math.max(0, Number(data.active_homework || 0)),
  });
  if (!lesson) return;
  const diff = (lesson.start.getTime() - Date.now()) / 60000;
  for (const minutes of REMINDER_MINUTES) {
    if (diff <= minutes && diff > minutes - 1.5) notifyLesson(lesson, minutes);
  }
  if (diff <= 0 && diff > -2) notifyLesson(lesson, 0);
}
function install() {
  app.on('adelia-notifications-enabled', value => { notificationsEnabled = value !== false; });
  app.whenReady().then(() => {
    setTimeout(() => poll().catch(() => {}), 8000);
    timer = setInterval(() => poll().catch(() => {}), POLL_MS);
  });
  app.on('before-quit', () => { if (timer) clearInterval(timer); });
}
function getLastLesson() { return publicLesson(lastLesson); }
module.exports = { install, getLastLesson, showLesson, poll, isStudentCabinetUrl };
