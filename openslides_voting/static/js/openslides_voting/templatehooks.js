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
    'Config',
    'UserForm',
    'DelegateForm',
    'PollCreateForm',
    'ngDialog',
    'MotionPollType',
    'AssignmentPollType',
    'Voter',
    'VotingPrinciple',
    'ErrorMessage',
    function ($http, templateHooks, operator, User, Keypad, VotingProxy, Delegate,
        Config, UserForm, DelegateForm, PollCreateForm, ngDialog, MotionPollType,
        AssignmentPollType, Voter, VotingPrinciple, ErrorMessage) {
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
                    $http.post('/rest/openslides_voting/motion-poll-ballot/recount_votes/', {poll_id: scope.poll.id});
                };
                scope.$watch(function () {
                    return MotionPollType.lastModified();
                }, function () {
                    var pollTypes = MotionPollType.filter({poll_id: scope.poll.id});
                    scope.pollType = pollTypes.length >= 1 ? pollTypes[0].displayName : 'Analog voting';
                    scope.isAnalogPoll = (pollTypes.length === 0 || pollTypes[0].type === 'analog');
                });
                scope.$watch(function () {
                    return VotingPrinciple.lastModified();
                }, function () {
                    scope.hasPrinciple = _.some(VotingPrinciple.getAll(), function (p) {
                        return _.includes(p.motions_id, scope.poll.motion.id);
                    });
                });
            },
        });
        templateHooks.registerHook({
            id: 'itemDetailListOfSpeakersButtons',
            templateUrl: 'static/templates/openslides_voting/item-detail-list-of-speakers-buttons-hook.html',
        });
        templateHooks.registerHook({
            id: 'userListExtraContent',
            templateUrl: 'static/templates/openslides_voting/user-list-extra-content-hook.html',
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
                        var delegateCount = Delegate.getDelegates().length;
                        scope.attendingCount = Keypad.filter({ 'user.is_present': true }).length;
                        scope.representedCount = VotingProxy.getAll().length;
                        scope.absentCount = Math.max(0,
                            delegateCount - scope.attendingCount - scope.representedCount);
                    }
                };
            },
        });
        templateHooks.registerHook({
            id: 'motionPollNewVoteButton',
            scope: function (scope) {
                scope.create_poll = function () {
                    if (operator.hasPerms('openslides_voting.can_manage')) {
                        ngDialog.open(PollCreateForm.getDialog(scope.motion,
                            function (pollId) {
                                ngDialog.open({
                                    template: 'static/templates/motions/motion-poll-form.html',
                                    controller: 'MotionPollUpdateCtrl',
                                    className: 'ngdialog-theme-default',
                                    closeByEscape: false,
                                    closeByDocument: false,
                                    resolve: {
                                        motionpollId: function () {
                                            return pollId;
                                        },
                                        voteNumber: function () {
                                            return scope.motion.polls.length;
                                        }
                                    }
                                });
                            }, function (error) {
                                scope.alert = ErrorMessage.forAlert(error);
                            }
                        ));
                    } else {
                         $http.post('/rest/motions/motion/' + scope.motion.id + '/create_poll/', {}).then(function (success) {
                            MotionPollType.create({
                                poll_id: success.data.createdPollId,
                                type: Config.get('voting_default_voting_type').value,
                            });
                        });
                    }
                };
            },
        });
        templateHooks.registerHook({
            id: 'motionPollVotingHeader',
            scope: function (scope) {
                return {
                    getActivePoll: function () {
                        return Voter.motionPollIdForMotion(scope.motion);
                    },
                    getVoteForActivePoll: function () {
                        var vote = Voter.motionPollVoteForMotion(scope.motion);
                        if (vote === 'Y') {
                            vote = 'Yes';
                        } else if (vote === 'N') {
                            vote = 'No';
                        } else if (vote === 'A') {
                            vote = 'Abstain';
                        }
                        return vote;
                    },
                };
            },
            templateUrl: 'static/templates/openslides_voting/motion-poll-voting-header-hook.html',
        });
        templateHooks.registerHook({
            id: 'assignmentPollFormButtons',
            templateUrl: 'static/templates/openslides_voting/assignment-poll-form-buttons-hook.html',
        });
        templateHooks.registerHook({
            id: 'assignmentPollNewBallotButton',
            scope: function (scope) {
                scope.createBallot = function () {
                    if (operator.hasPerms('openslides_voting.can_manage')) {
                        ngDialog.open(PollCreateForm.getDialog(scope.assignment,
                            function (pollId) {
                                ngDialog.open({
                                    template: 'static/templates/assignments/assignmentpoll-form.html',
                                    controller: 'AssignmentPollUpdateCtrl',
                                    className: 'ngdialog-theme-default',
                                    closeByEscape: false,
                                    closeByDocument: false,
                                    resolve: {
                                        assignmentpollId: function () {
                                            return pollId;
                                        },
                                        ballot: function () {
                                            return scope.assignment.polls.length;
                                        },
                                    }
                                });
                            }, function (error) {
                                scope.alert = ErrorMessage.forAlert(error);
                            }
                        ));
                    } else {
                         $http.post('/rest/assignments/assignment/' + scope.assignment.id +
                             '/create_poll/', {}).then(function (success) {
                            if (assignment.phase === 0) {
                                scope.updatePhase(1);
                            }

                            AssignmentPollType.create({
                                poll_id: success.data.createdPollId,
                                type: Config.get('voting_default_voting_type').value,
                            });
                        });
                    }
                };
            },
        });
        templateHooks.registerHook({
            id: 'assignmentPollSmallButtons',
            templateUrl: 'static/templates/openslides_voting/assignment-poll-small-buttons-hook.html',
            scope: function (scope) {
                // Recalculate vote result.
                scope.countVotes = function () {
                    //$http.post('/voting/count/' + scope.poll.id + '/');
                    throw "TODO";
                };
                scope.$watch(function () {
                    return AssignmentPollType.lastModified();
                }, function () {
                    var pollTypes = AssignmentPollType.filter({poll_id: scope.poll.id});
                    scope.pollType = pollTypes.length >= 1 ? pollTypes[0].displayName : 'Analog voting';
                    scope.isAnalogPoll = (pollTypes.length === 0 || pollTypes[0].type === 'analog');
                });
                scope.$watch(function () {
                    return VotingPrinciple.lastModified();
                }, function () {
                    scope.hasPrinciple = _.some(VotingPrinciple.getAll(), function (p) {
                        return _.includes(p.assignments_id, scope.poll.assignment.id);
                    });
                });
            },
        });
    }
]);

}());
