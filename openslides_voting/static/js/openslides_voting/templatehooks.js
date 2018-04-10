(function () {

'use strict';

angular.module('OpenSlidesApp.openslides_voting.templatehooks', [
    'OpenSlidesApp.openslides_voting'
])

// Template hooks
.run([
    '$http',
    'templateHooks',
    'operator',
    'User',
    'Keypad',
    'VotingProxy',
    'Delegate',
    'UserForm',
    'DelegateForm',
    'PollCreateForm',
    'ngDialog',
    'MotionPollType',
    function ($http, templateHooks, operator, User, Keypad, VotingProxy, Delegate,
        UserForm, DelegateForm, PollCreateForm, ngDialog, MotionPollType) {
        templateHooks.registerHook({
            id: 'motionPollFormButtons',
            templateUrl: 'static/templates/openslides_voting/motion-poll-form-buttons-hook.html',
        });
        templateHooks.registerHook({
            id: 'motionPollSmallButtons',
            templateUrl: 'static/templates/openslides_voting/motion-poll-small-buttons-hook.html',
            scope: function (scope) {
                // Recalculate vote result.
                scope.countVotes = function () {
                    $http.post('/voting/count/' + scope.poll.id + '/');
                };
                scope.$watch(function () {
                    return MotionPollType.lastModified();
                }, function () {
                    var pollTypes = MotionPollType.filter({poll_id: scope.poll.id});
                    scope.pollType = pollTypes.length >= 1 ? pollTypes[0].displayName : 'Analog voting';
                });
            },
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
        templateHooks.registerHook({
            id: 'motionPollNewVoteButton',
            scope: function (scope) {
                scope.create_poll = function () {
                    if (operator.hasPerms('openslides_voting.can_manage')) {
                        ngDialog.open(PollCreateForm.getDialog(scope.motion));
                    } else {
                         $http.post('/rest/motions/motion/' + scope.motion.id + '/create_poll/', {});
                    }
                };
            },
        });
        templateHooks.registerHook({
            id: 'motionListMenuButton',
            template: '<a ui-sref="openslides_voting.tokens"' +
                        'class="btn btn-default btn-sm">' +
                        '<translate>Tokens</translate>' +
                      '</button>',
        });
        templateHooks.registerHook({
            id: 'assignmentListMenuButton',
            template: '<a ui-sref="openslides_voting.tokens"' +
                        'class="btn btn-default btn-sm">' +
                        '<translate>Tokens</translate>' +
                      '</button>',
        });
    }
]);

}());
