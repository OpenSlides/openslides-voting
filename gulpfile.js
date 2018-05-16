/**
 * Gulp tasks for openslides voting plugin.
 *
 * Run `./node_modules/.bin/gulp` for all default task and
 * `./node_modules/.bin/gulp watch` during development
 *
 */

// TODO: Remove the next line when support for Node 0.10.x is dropped.
// See https://github.com/postcss/postcss#nodejs-010-and-the-promise-api
require('es6-promise').polyfill();

var argv = require('yargs').argv,
    concat = require('gulp-concat'),
    gulp = require('gulp'),
    gettext = require('gulp-angular-gettext'),
    gulpif = require('gulp-if'),
    jshint = require('gulp-jshint'),
    mainBowerFiles = require('main-bower-files'),
    path = require('path'),
    sourcemaps = require('gulp-sourcemaps'),
    templateCache = require('gulp-angular-templatecache'),
    uglify = require('gulp-uglify');


/**
 * Default tasks to be run before start.
 */

// Catches all template files concats them to one file js/templates.js.
gulp.task('templates', function () {
    return gulp.src(path.join('**', 'static', 'templates', '**', '*.html'))
        .pipe(templateCache('templates.js', {
            module: 'OpenSlidesApp.openslides_voting.templates',
            standalone: true,
            moduleSystem: 'IIFE',
            transformUrl: function (url) {
                var pathList = url.split(path.sep);
                pathList.shift();
                return pathList.join(path.sep);
            },
        }))
        .pipe(gulp.dest(path.join('openslides_voting', 'static', 'js', 'openslides_voting')));
});

gulp.task('js-libs', function () {
    return gulp.src(mainBowerFiles({
            filter: /\.js$/
        }))
        .pipe(sourcemaps.init())
        .pipe(concat('libs.js'))
        .pipe(sourcemaps.write())
        .pipe(gulpif(argv.production, uglify()))
        .pipe(gulp.dest(path.join('openslides_voting', 'static', 'js', 'openslides_voting')));
});

// Compiles translation files (*.po) to *.json and saves them in the directory 'i18n'.
gulp.task('translations', function () {
    return gulp.src(path.join('openslides_voting', 'locale', 'angular-gettext', '*.po'))
        .pipe(gettext.compile({
            format: 'json'
        }))
        .pipe(gulp.dest(path.join('openslides_voting', 'static', 'i18n', 'openslides_voting')));
});

// Gulp default task. Runs all other tasks before.
gulp.task('default', ['translations', 'templates', 'js-libs'], function () {});

// Watches changes in JavaScript and templates.
gulp.task('watch', ['templates'], function   () {
    gulp.watch([
        path.join('**', 'static', 'templates', '**', '*.html')
    ], ['templates']);
});


/**
 * Extra tasks that have to be called manually. Useful for development.
 */

// Extracts translatable strings using angular-gettext and saves them in file
// locale/angular-gettext/template-en.pot.
gulp.task('pot', function () {
    return gulp.src([
            'openslides_voting/static/templates/*/*.html',
            'openslides_voting/static/js/*/*.js',
        ])
        .pipe(gettext.extract('template-en.pot', {}))
        .pipe(gulp.dest(path.join('openslides_voting', 'locale', 'angular-gettext')));
});

// Checks JavaScript using JSHint
gulp.task('jshint', function () {
    return gulp.src([
            'gulpfile.js',
            path.join( 'openslides_voting', 'static', 'js', 'openslides_voting', '*.js' ),
        ])
        .pipe(jshint())
        .pipe(jshint.reporter('default'))
        .pipe(jshint.reporter('fail'));
});
