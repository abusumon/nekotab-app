const isProduction = (process.env.NODE_ENV || '').trim() === 'production';

module.exports = {
  // Output to standard directory; this is then compiled by django collectstatic
  outputDir: './tabbycat/static/vue/',
  // Need to set baseUrl for hot module reloading (proxies to the local server)
  // But want to disable this when building for production
  publicPath: isProduction ?
    '/static/vue/'
    : 'http://localhost:8888',
  // Don't add a hash to the filename
  filenameHashing: false,
  // We use <templates> in components; so need to include the compile
  runtimeCompiler: true,
  // Must output chunks to the same directory so async loading works
  configureWebpack: {
    output: {
      chunkFilename: '[name].js'
    }
  },
  lintOnSave: !isProduction, // Lint if not in production
  // Allow code splitting for lazy-loaded components
  chainWebpack: config => {
    config.optimization.splitChunks({
      chunks: 'async',
    })
  },
  devServer: {
    port: 8888,
    headers: {
      'Access-Control-Allow-Origin': '*' // Allow hot module reload
    }
  },
  pages: {
    app: {
    entry: 'tabbycat/templates/js-bundles/main.js'
    }
  },
  pluginOptions: {
    webpackBundleAnalyzer: {
      analyzerMode: 'disabled', // Disabled for speed
      defaultSizes: 'gzip', // Show the filesizes as if gzipped
      openAnalyzer: false // Enable to view a heatmap of dependency sizes
    }
  }
}
