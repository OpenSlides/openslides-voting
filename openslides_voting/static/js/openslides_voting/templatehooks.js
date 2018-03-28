(function () {

'use strict';

angular.module('OpenSlidesApp.openslides_voting.templatehooks', [
    'OpenSlidesApp.openslides_voting'
])

// Template hooks
.run([
    'templateHooks',
    'User',
    'Keypad',
    'VotingProxy',
    'Delegate',
    'UserForm',
    'DelegateForm',
    'ngDialog',
    function (templateHooks, User, Keypad, VotingProxy, Delegate, UserForm,
        DelegateForm, ngDialog) {
        templateHooks.registerHook({
            id: 'motionPollFormButtons',
            templateUrl: 'static/templates/openslides_voting/motion-poll-form-buttons-hook.html',
        });
        templateHooks.registerHook({
            id: 'motionPollSmallButtons',
            templateUrl: 'static/templates/openslides_voting/motion-poll-small-buttons-hook.html',
        });
        templateHooks.registerHook({
            id: 'itemDetailListOfSpeakersButtons',
            templateUrl: 'static/templates/openslides_voting/item-detail-list-of-speakers-buttons-hook.html',
        });
        templateHooks.registerHook({
            id: 'userListExtraContentColumn',
            templateUrl: 'static/templates/openslides_voting/user-list-extra-content-column-hook.html',
        });
        templateHooks.registerHook({
            id: 'userListEditButton',
            scope: {
                openDialog: function (user) {
                    if (Delegate.isDelegate(user)) {
                        ngDialog.open(DelegateForm.getDialog(user));
                    } else {
                        ngDialog.open(UserForm.getDialog(user));
                    }
                }
            },
        });
        templateHooks.registerHook({
            id: 'userListMenuButtons',
            templateUrl: 'static/templates/openslides_voting/user-list-menu-buttons-hook.html',
        });
        templateHooks.registerHook({
            id: 'userListTableStats',
            templateUrl: 'static/templates/openslides_voting/user-list-table-stats-hook.html',
            scope: function (scope) {
                return {
                    updateTableStats: function () {
                        var delegateCount = User.filter({groups_id: 2}).length;
                        scope.attendingCount = Keypad.filter({ 'user.is_present': true }).length;
                        scope.representedCount = VotingProxy.getAll().length;
                        scope.absentCount = Math.max(0,
                            delegateCount - scope.attendingCount - scope.representedCount);
                    }
                };
            },
        });
        templateHooks.registerHook({
            id: 'userListSubmenuRight',
            template: '<button class="btn btn-default btn-sm spacer-right pull-right"' +
                        'ng-click="filter.multiselectFilters.group = [2]" type="button">' +
                        '<translate>Show delegates</translate>' +
                      '</button>',
        });
    }
]);

}());
