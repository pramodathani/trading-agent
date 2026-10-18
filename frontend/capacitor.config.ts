import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.pramodathani.tradingagent',
  appName: 'Trading Agent',
  webDir: 'dist',
  backgroundColor: '#151515',
  android: {
    allowMixedContent: false,
  },
  plugins: {
    SystemBars: {
      insetsHandling: 'css',
      initialViewportFitValueHint: 'cover',
    },
    Keyboard: {
      resizeOnFullScreen: true,
    },
    SplashScreen: {
      launchShowDuration: 600,
      backgroundColor: '#151515',
      showSpinner: false,
    },
  },
};

export default config;
