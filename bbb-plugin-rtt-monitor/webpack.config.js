const CopyWebpackPlugin = require('copy-webpack-plugin');
const { execSync } = require('child_process');
const path = require('path');

const gitHash = execSync('git rev-parse --short HEAD').toString().trim();
const jsFilename = `RttMonitor-${gitHash}.js`;

module.exports = {
  entry: './src/index.tsx',
  output: {
    filename: jsFilename,
    library: 'RttMonitor',
    libraryTarget: 'umd',
    publicPath: '/',
    globalObject: 'this',
    clean: true,
  },
  experiments: {
    topLevelAwait: true,
  },
  devServer: {
    allowedHosts: 'all',
    port: 4702,
    host: '0.0.0.0',
    hot: false,
    liveReload: false,
    client: {
      overlay: false,
    },
    setupMiddlewares: (middlewares, devServer) => {
      if (!devServer) {
        throw new Error('webpack-dev-server is not defined');
      }
      devServer.app.get('/manifest.json', (req, res) => {
        res.sendFile(path.resolve(__dirname, 'manifest.json'));
      });
      return middlewares;
    },
  },
  module: {
    rules: [
      {
        test: /\.(js|jsx)$/,
        exclude: /node_modules/,
        use: {
          loader: 'babel-loader',
        },
      },
      {
        test: /\.css$/,
        use: ['style-loader', 'css-loader'],
      },
      {
        test: /\.tsx?$/,
        use: 'ts-loader',
        exclude: /node_modules/,
      },
    ],
  },
  resolve: {
    extensions: ['.js', '.jsx', '.tsx', '.ts'],
  },
  plugins: [
    new CopyWebpackPlugin({
      patterns: [
        {
          from: 'manifest.json',
          to: './',
          transform(content) {
            const manifest = JSON.parse(content);
            manifest.javascriptEntrypointUrl = jsFilename;
            return JSON.stringify(manifest, null, 2) + '\n';
          },
        },
        { from: 'locales', to: './locales' },
      ],
    }),
  ],
};
