Instruction to update translations for OpenSlides-Voting-Plugin (JavaScipt and Django):
---------------------------------------------------------------------------------------

1. Update English resource files:

   a) for JavaScript run:
      $ ./node_modules/.bin/gulp pot
      -> updates 'openslides_voting/locale/angular-gettext/template-en.pot'

   b) for Django:
      $ cd openslides_voting
      $ django-admin.py makemessages -l en
      -> updates 'openslides_voting/locale/en/LC_MESSAGES/django.po'

2. Upload and translate both files in transifex into desired languages.
   https://www.transifex.com/openslides/openslides-voting

3. Download translated po files for each language.
   a) openslides_voting/locale/angular-gettext/{LANG-CODE}.po
   b) openslides_voting/locale/{LANG-CODE}/LC_MESSAGES/django.po

4. Create mo file for each language (only for django po files required)
   $ cd openslides_voting
   $ django-admin.py compilemessages

5. Create json file for each language
   $ cd ~/openslides-voting
   $ ./node_modules/.bin/gulp translations
   -> creates static/i18n/openslides_voting/{LANG-CODE}.json

6. Commit for each language the following files:
   a) openslides_voting/locale/angular-gettext/template-en.pot
      openslides_voting/locale/angular-gettext/{LANG-CODE}.po
   b) openslides_voting/locale/en/LC_MESSAGES/django.po
      openslides_voting/locale/{LANG-CODE}/LC_MESSAGES/django.po
      openslides_voting/locale/{LANG-CODE}/LC_MESSAGES/django.mo
