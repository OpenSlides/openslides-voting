Instruction to update translations for OpenSlides (JavaScipt and Django):
-------------------------------------------------------------------------

1. Install gulp
   $ cd ~/openslides-voting
   Create gulpfile.js (copy from openslides-votecollector and update)
   npm install gulp (and dependencies: es6-promise gulp-angular-gettext gulp-jshint path)

2. Update English resource files:

   a) for JavaScript run:
      $ ./node_modules/.bin/gulp pot
      -> updates 'openslides_voting/locale/angular-gettext/template-en.pot'

   b) for Django:
      $ cd openslides_voting
      $ django-admin.py makemessages -l en
      -> updates 'openslides_voting/locale/en/LC_MESSAGES/django.po'

3. Create and translate.
   a) openslides_voting/locale/angular-gettext/de.po
   b) openslides_voting/locale/de/LC_MESSAGES/django.po

4. Create mo file for each language (only for django po files required)
   $ cd openslides_voting
   $ django-admin.py compilemessages

6. Create json
   $ cd ~/openslides-voting
   $ ./node_modules/.bin/gulp translations
   -> creates static/i18n/openslides_voting/de.json

7. Collect statics for production server
