'use strict';
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('adeliaDesktop', Object.freeze({
  platform: process.platform,
  desktop: true,
  openLessonTool: (kind, url) => ipcRenderer.invoke('adelia:lesson-tool', { kind, url }),
  endLessonWorkspace: () => ipcRenderer.invoke('adelia:end-lesson-workspace'),
  openRoute: (route, id = '') => ipcRenderer.invoke('adelia:open-route', { route, id }),
  openDeviceCheck: lessonId => ipcRenderer.invoke('adelia:device-check', { lessonId: String(lessonId || '') }),
  openAbout: () => ipcRenderer.invoke('adelia:open-about'),
  getPreferences: () => ipcRenderer.invoke('adelia:desktop-prefs'),
  setCloseToTray: value => ipcRenderer.invoke('adelia:set-close-to-tray', !!value),
  getUxState: () => ipcRenderer.invoke('adelia:ux-state'),
  setNotifications: value => ipcRenderer.invoke('adelia:set-notifications', !!value),
  updateDashboardState: state => ipcRenderer.invoke('adelia:dashboard-state', state || {}),
  setAutostart: value => ipcRenderer.invoke('adelia:set-autostart', !!value),
  setHotkey: value => ipcRenderer.invoke('adelia:set-hotkey', !!value),
  showMain: () => ipcRenderer.invoke('adelia:show-main'),
  getLessonLayout: () => ipcRenderer.invoke('adelia:lesson-layout-state'),
  setLessonLayout: mode => ipcRenderer.invoke('adelia:lesson-layout', String(mode || 'together')),
  toggleLessonVideo: () => ipcRenderer.invoke('adelia:lesson-toggle-video'),
  showRoleChooser: () => ipcRenderer.invoke('adelia:role-chooser'),
  teacherLogin: code => ipcRenderer.invoke('adelia:teacher-login', String(code || '')),
  openStudentLogin: mode => ipcRenderer.invoke('adelia:student-login', String(mode || 'password')),
  openParentCabinet: () => ipcRenderer.invoke('adelia:parent-cabinet'),
  openTeacherCabinet: () => ipcRenderer.invoke('adelia:teacher-cabinet'),
  onboardingStart: payload => ipcRenderer.invoke('adelia:onboarding-start', payload || {}),
  onboardingStatus: token => ipcRenderer.invoke('adelia:onboarding-status', String(token || '')),
  onboardingRegion: payload => ipcRenderer.invoke('adelia:onboarding-region', payload || {}),
  onboardingScheduleOptions: token => ipcRenderer.invoke('adelia:onboarding-schedule-options', String(token || '')),
  onboardingSchedule: payload => ipcRenderer.invoke('adelia:onboarding-schedule', payload || {}),
  onboardingComplete: payload => ipcRenderer.invoke('adelia:onboarding-complete', payload || {})
}));