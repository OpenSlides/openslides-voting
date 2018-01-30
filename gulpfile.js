/**
 * Gulp tasks for openslides votecollector plugin.
 *
 * Run
 *
 *      $ ./node_modules/.bin/gulp
 *
 */

// TODO: Remove the next line when support for Node 0.10.x is dropped.
// See https://github.com/postcss/postcss#nodejs-010-and-the-promise-api
require('es6-promise').polyfill();

var gulp = require('gulp'),
    gettext = require('gulp-angular-gettext'),
    jshint = require('gulp-jshint'),
    path = require('path')


/**
 * Default tasks to be run before start.
 */

// Compiles translation files (*.po) to *.json and saves them in the directory 'i18n'.
gulp.task('translations', function () {
    return gulp.src(path.join('openslides_voting', 'locale', 'angular-gettext', '*.po'))
        .pipe(gettext.compile({
            format: 'json'
        }))
        .pipe(gulp.dest(path.join('openslides_voting', 'static', 'i18n', 'openslides_voting')));
});

// Gulp default task. Runs all other tasks before.
gulp.task('default', ['translations'], function () {});


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
            path.join( 'openslides_voting', 'static', '*', '*.js' ),
        ])
        .pipe(jshint())
        .pipe(jshint.reporter('default'))
        .pipe(jshint.reporter('fail'));
});
