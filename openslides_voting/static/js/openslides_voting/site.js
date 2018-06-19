(function () {

'use strict';

angular.module('OpenSlidesApp.openslides_voting.site', [
    'OpenSlidesApp.openslides_voting',
    'OpenSlidesApp.openslides_voting.templatehooks',
    'OpenSlidesApp.openslides_voting.pdf'
])

.config([
    '$stateProvider',
    'gettext',
    function ($stateProvider, gettext) {
        $stateProvider
        .state('openslides_voting', {
            url: '/voting',
            abstract: true,
            template: '<ui-view/>',
            basePermission: 'openslides_voting.can_manage',
        })
        .state('openslides_voting.attendance', {
            url: '/attendance',
            controller: 'AttendanceCtrl',
            data: {
                title: gettext('Attendance'),
            },
        })
        .state('openslides_voting.tokens', {
            url: '/tokens',
            templateUrl: '/static/templates/openslides_voting/tokens.html',
            controller: 'TokensCtrl',
            data: {
                title: gettext('Voting tokens'),
            },
        })
        .state('openslides_voting.shares', {
            url: '/shares',
            abstract: true,
            template: '<ui-view/>',
            data: {
                title: gettext('Shares'),
            },
        })
        .state('openslides_voting.shares.list', {})
        .state('openslides_voting.shares.import', {
            url: '/import',
            controller: 'SharesImportCtrl',
        })
        .state('openslides_voting.keypad', {
            url: '/keypad',
            abstract: true,
            template: '<ui-view/>',
            data: {
                title: gettext('Keypads'),
            },
        })
        .state('openslides_voting.keypad.list', {})
        .state('openslides_voting.keypad.import', {
            url: '/import',
            controller: 'KeypadImportCtrl'
        })
        .state('openslides_voting.absenteeVote', {
            url: '/absenteevote',
            abstract: true,
            template: '<ui-view/>',
            data: {
                title: gettext('Absentee votes'),
            },
        })
        .state('openslides_voting.absenteeVote.list', {})
        .state('openslides_voting.absenteeVote.import', {
            url: '/import',
            controller: 'AbsenteeVoteImportCtrl'
        })
        .state('openslides_voting.motionPoll', {
            abstract: true,
            template: '<ui-view/>',
            data: {
                title: gettext('Motion poll'),
            },
        })
        .state('openslides_voting.motionPoll.detail', {
            url: '/motionpoll/{id:int}',
            controller: 'MotionPollVoteDetailCtrl',
        })
        .state('openslides_voting.assignmentPoll', {
            abstract: true,
            template: '<ui-view/>',
            data: {
                title: gettext('Assignment poll'),
            },
        })
        .state('openslides_voting.assignmentPoll.detail', {
            url: '/assignmentpoll/{id:int}',
            controller: 'AssignmentPollVoteDetailCtrl',
        })

        // votes enter states
        .state('submit_votes', {
            abstract: true,
            template: '<ui-view/>',
            data: {
                title: gettext('OpenSlides-Voting'),
            },
        })
        .state('submit_votes.motionPoll', {
            url: '/motionpoll/submit/{id:int}',
            templateUrl: '/static/templates/openslides_voting/submit-motion-poll.html',
            controller: 'MotionPollSubmitCtrl',
        })
        .state('submit_votes.assignmentPoll', {
            url: '/assignmentpoll/submit/{id:int}',
            templateUrl: '/static/templates/openslides_voting/submit-assignment-poll.html',
            controller: 'AssignmentPollSubmitCtrl',
        })
        .state('submit_votes.token_entry', {
            url: '/token/submit',
            controller: 'TokenSubmitCtrl',
            templateUrl: '/static/templates/openslides_voting/submit-token.html',
            data: {
                basePerm: 'openslides_voting.can_see_token_voting',
            },
        });
    }
])

.run([
    '$state',
    '$timeout',
    '$rootScope',
    'operator',
    'gettextCatalog',
    'Messaging',
    function ($state, $timeout, $rootScope, operator, gettextCatalog, Messaging) {
        var lockInterface = function () {
            $state.transitionTo('submit_votes.token_entry');
            // Remove the header controls, navigation, projector sidebar and the footer
            $('#header .user').remove();
            $('#nav').remove();
            $('#footer').remove();
            // Wait for angular to finish the dom..
            $timeout(function () {
                $('#sidebar').remove();
            });

            // Prevent state changes
            $rootScope.$on('$stateChangeStart', function (event, toState) {
                if (toState.name !== 'submit_votes.token_entry') {
                    event.preventDefault();
                }
            })
        };

        var notifyUser = function () {
            var message = gettextCatalog.getString('Your permissions are misconfigurated. '
                + 'Please contact your systemadministrator or read the manual about the permissions'
                + ' needed for the token voting mode.');
            Messaging.addMessage(message, 'error', {noClose: true});
        };

        operator.registerSetUserCallback(function (user) {
            if (operator.hasPerms('openslides_voting.can_see_token_voting')) {
                // Check, if he has the required can_see_assignments and can_see_motions
                if (operator.hasPerms('motions.can_see') && operator.hasPerms('assignments.can_see')) {
                    if (operator.perms.length > 3) {
                        // Wohoo, the user has all required perms, but some more. This is not
                        // as expected. Panic, now!
                        notifyUser();
                    } else {
                        lockInterface();
                    }
                } else {
                    // Panic here, too!
                    notifyUser();
                }
            }
        });
    }
])

.controller('TokenSubmitCtrl', [
    '$scope',
    '$http',
    '$timeout',
    '$interval',
    '$filter',
    'AuthorizedVoters',
    'VotingSettings',
    'gettextCatalog',
    'ErrorMessage',
    function ($scope, $http, $timeout, $interval, $filter, AuthorizedVoters,
        VotingSettings, gettextCatalog, ErrorMessage) {
        // All states: 'scan' -> 'enter' -> 'submitted'
        $scope.votingState = 'scan';
        $scope.alert = {};
        $scope.showGray = true; // For the generic ng-include for motion poll buttons

        var token, timeoutInterval;

        $scope.$watch(function () {
            return AuthorizedVoters.lastModified();
        }, function () {
            if ($scope.votingState === 'enter') {
                // Notify the one, who enters the votes.
                // TODO
            } else {
                $scope.av = AuthorizedVoters.get(1);
                $scope.isTokenVoting =  (($scope.av.motionPoll || $scope.av.assignmentPoll) &&
                    $scope.av.type === 'token_based_electronic');
            }
        });

        var resetInput = function () {
            $scope.tokenInput = '';
            $scope.tokenInputDisabled = false;
            $timeout(function () {
                $('#tokenInput').focus();
            });
        };

        $scope.scan = function () {
            if ($scope.votingState !== 'scan') {
                return;
            }

            $scope.tokenInputDisabled = true;
            token = $scope.tokenInput;
            $http.post('/rest/openslides_voting/voting-token/check_token/', {token: token}).then(function (success) {
                if (success.data) {
                    $scope.alert = {};
                    startVoting();
                } else {
                    $scope.alert = {
                        msg: gettextCatalog.getString('The token is not valid.'),
                        type: 'danger',
                        show: true,
                    };
                }
                resetInput();
            }, function (error) {
                $scope.alert = ErrorMessage.forAlert(error);
                resetInput();
            });
        };

        var startVoting = function () {
            $scope.votingState = 'enter';

            if ($scope.av.assignmentPoll) {
                $scope.poll = $scope.av.assignmentPoll;
                // prepare the votes model
                $scope.votes = {};
                if ($scope.poll.pollmethod === 'votes') {
                    $scope.votes.candidateIndex = -1;
                } else {
                    _.forEach($scope.poll.options, function (option) {
                        $scope.votes[option.candidate.id] = 'N';
                    });
                }
            }
        };

        // This function is called, if a motion poll option is clicked
        $scope.vote = function (vote) {
            $scope.alert = {};
            $scope.mpbVote = {
                value: vote,
                token: token,
            };
        };

        // This function submitts the vote
        $scope.submitVote = function () {
            $scope.alert = {};
            if ($scope.av.motionPoll) {
                $http.post('/votingcontroller/vote/' + $scope.av.motionPoll.id + '/', $scope.mpbVote).then(
                    function (success) {
                        startSubmit(success.data);
                    }, function (error) {
                        $scope.alert = ErrorMessage.forAlert(error);
                    }
                );
            } else {
                var vote = {
                    token: token,
                };
                var route;
                if ($scope.poll.pollmethod === 'votes') {
                    route = 'candidate';
                    vote.value = $scope.votes.candidateIndex;
                    if (vote.value <= 0 || vote.value > $scope.poll.options.length) {
                        $scope.alert = {
                            msg: gettextCatalog.getString('Please select a candidate'),
                            type: 'danger',
                            show: true,
                        };
                        return;
                    }
                } else {
                    route = 'vote';
                    vote.value = $scope.votes;
                }
                $http.post('/votingcontroller/' + route + '/' + $scope.poll.id + '/', vote).then(
                    function (success) {
                        startSubmit(success.data);
                    }, function (error) {
                        $scope.alert = ErrorMessage.forAlert(error);
                    }
                );
            }
        };

        // Change into submitted state
        var startSubmit = function (resultData) {
            $scope.resultToken = resultData.result_token;
            $scope.resultVote = resultData.result_vote;
            $scope.votingState = 'submitted';
            var timeout = VotingSettings.votingResultTokenTimeout;
            if (timeout) {
                $scope.timeout = timeout;
                timeoutInterval = $interval(function () {
                    $scope.timeout--;
                    if ($scope.timeout <= 0) {
                        $scope.reset();
                    }
                }, 1000);
            }
        };

        // Returns the voted candidate.
        $scope.getResultCandidate = function () {
            var optionIndex = parseInt($scope.resultVote);
            var poll = $scope.av.assignmentPoll;
            var option = $filter('orderBy')(poll.options, 'weight')[optionIndex-1];
            if (option) {
                return option.candidate.full_name;
            }
        };

        $scope.reset = function () {
            $interval.cancel(timeoutInterval);
            $scope.timeout = 0;
            $scope.alert = {};
            $scope.mpbVote = void 0;
            $scope.poll = void 0;
            $scope.resultToken = void 0;
            $scope.resultVote = void 0;
            token = void 0;
            $scope.votingState = 'scan';
            resetInput();
        };
    }
])

// Overrides the UserForm. Adds fields for keypads, proxies, ...
.factory('DelegateForm', [
    'gettextCatalog',
    'UserForm',
    'VotingPrinciple',
    'Delegate',
    'Config',
    function (gettextCatalog, UserForm, VotingPrinciple, Delegate, Config) {
        return {
            getDialog: function (user) {
                return {
                    template: 'static/templates/openslides_voting/delegate-form.html',
                    controller: 'UserUpdateCtrl', // Use the original controller. Our custom controller
                    // is initialized in the template.
                    className: 'ngdialog-theme-default wide-form',
                    closeByEscape: false,
                    closeByDocument: false,
                    resolve: {
                        userId: function () {
                            return user.id;
                        }
                    }
                };
            },
            getFormFields: function (user) {
                var formFields = UserForm.getFormFields();
                var otherDelegates = _.orderBy(
                    _.filter(Delegate.getDelegates(), function (delegate) {
                        return delegate.id !== user.id;
                    }),
                    'full_name'
                );
                var vcEnabled = Config.get('voting_enable_votecollector').value;
                var principlesEnabled = Config.get('voting_enable_principles').value;
                var proxiesEnabled = Config.get('voting_enable_proxies').value;
                if (!vcEnabled && !principlesEnabled && !proxiesEnabled) {
                    return formFields;
                }

                var newFormFields = [
                    {
                        template: '<hr class="smallhr">',
                    }
                ];
                if (vcEnabled) {
                    newFormFields.push({
                        key: 'keypad_number',
                        type: 'input',
                        templateOptions: {
                            label: gettextCatalog.getString('Keypad'),
                            type: 'number'
                        },
                        watcher: {
                            listener: function (field, newValue, oldValue, formScope) {
                                if (newValue) {
                                    formScope.model.proxy_id = null;
                                    formScope.options.formState.notRegistered = false;
                                }
                                else {
                                    formScope.model.is_present = false;
                                    formScope.options.formState.notRegistered = true;
                                }
                            }
                        }
                    });
                }
                if (proxiesEnabled) {
                    newFormFields = newFormFields.concat([
                    {
                        key: 'proxy_id',
                        type: 'select-single',
                        templateOptions: {
                            label: gettextCatalog.getString('Proxy'),
                            options: otherDelegates,
                            ngOptions: 'option.id as option.full_name for option in to.options',
                            placeholder: '(' + gettextCatalog.getString('No proxy') + ')'
                        },
                        watcher: {
                            listener: function (field, newValue, oldValue, formScope) {
                                if (newValue) {
                                    formScope.model.keypad_number = null;
                                }
                            }
                        }
                    },
                    {
                        key: 'mandates_id',
                        type: 'select-multiple',
                        templateOptions: {
                            label: gettextCatalog.getString('Principals'),
                            options: otherDelegates,
                            ngOptions: 'option.id as option.full_name for option in to.options',
                            placeholder: '(' + gettextCatalog.getString('No principals') + ')'
                        }
                    }
                    ]);
                }
                if (principlesEnabled) {
                    newFormFields = newFormFields.concat([
                    {
                        key: 'delegateMore',
                        type: 'checkbox',
                        templateOptions: {
                            label: gettextCatalog.getString('Show voting rights')
                        }
                    },
                    {
                        template: '<hr class="smallhr">',
                        hideExpression: '!model.delegateMore'
                    }
                    ]);

                    var fieldGroup = [];
                    _.forEach(VotingPrinciple.filter({orderBy: 'id'}), function (principle) {
                        fieldGroup.push({
                            key: 'shares[' + principle.id + ']',
                            type: 'input',
                            className: 'col-xs-2 no-padding-left',
                            templateOptions: {
                                label: principle.name,
                                type: 'number',
                                step: principle.step,
                                min: 0,
                            }
                        });
                        if (fieldGroup.length == 6) {
                            newFormFields.push({
                                className: 'row',
                                fieldGroup: fieldGroup,
                                hideExpression: '!model.delegateMore'
                            });
                            fieldGroup = [];
                        }
                    });
                    if (fieldGroup.length > 0) {
                        // TODO: Find a better way to deal with last col-xs.
                        var n = (6 - fieldGroup.length) * 2 + 2 ;
                        _.last(fieldGroup).className = 'no-padding-left col-xs-' + n;
                        newFormFields.push({
                            className: 'row',
                            fieldGroup: fieldGroup,
                            hideExpression: '!model.delegateMore'
                        });
                    }
                }
                return formFields.concat(newFormFields);
            }
        };
    }
])

// Manage creating a poll for a motion or assignment
.factory('PollCreateForm', [
    'gettextCatalog',
    'PollType',
    'Config',
    function (gettextCatalog, PollType, Config) {
        return {
            getDialog: function (obj, onSuccess, onError) {
                return {
                    template: 'static/templates/openslides_voting/poll-create-form.html',
                    controller: 'PollCreateCtrl',
                    className: 'ngdialog-theme-default wide-form',
                    closeByEscape: false,
                    closeByDocument: false,
                    resolve: {
                        objId: function () {
                            return obj.id;
                        },
                        resourceName: function () {
                            return obj.getResourceName();
                        },
                        onSuccess: function () {
                            return onSuccess;
                        },
                        onError: function () {
                            return onError;
                        },
                    },
                };
            },
            getFormFields: function (user) {
                return [
                {
                    key: 'votingType',
                    type: 'select-single',
                    templateOptions: {
                        label: gettextCatalog.getString('Type'),
                        options: PollType.getTypes(Config.get('voting_enable_votecollector').value),
                        ngOptions: 'option.key as option.displayName for option in to.options',
                        required: true,
                    }
                },
                ];
            },
        };
    }
])

.factory('Voter', [
    '$rootScope',
    'operator',
    'AuthorizedVoters',
    'MotionPollBallot',
    'AssignmentPollBallot',
    'Messaging',
    'gettextCatalog',
    function ($rootScope, operator, AuthorizedVoters, MotionPollBallot,
        AssignmentPollBallot, Messaging, gettextCatalog) {
        var av;
        var messageId;

        // Handles the message for the user
        // Look for explicit changes for the operator
        var oldIncluded = false;
        var oldHasVoted = false;
        var oldMotionPollId = null;
        var oldAssignmentPollId = null;
        var updateMessage = function () {
            if (!operator.user) {
                return;
            }

            av = AuthorizedVoters.get(1);
            // No av or no active voting
            if (!av || (!av.motion_poll_id && !av.assignment_poll_id)) {
                Messaging.deleteMessage(messageId);
                return;
            }

            var included = operator.user
                && _.includes(_.keys(av.authorized_voters), operator.user.id.toString());
            // This user is not affected by the current voting.
            if (!included) {
                Messaging.deleteMessage(messageId);
                oldIncluded = false;
                return;
            }

            var hasVoted;
            if (av.motion_poll_id) {
                hasVoted = _.find(MotionPollBallot.getAll(), function (mpb) {
                    return mpb.delegate_id === operator.user.id &&
                        mpb.poll_id === av.motion_poll_id;
                });
            } else { // assignment poll
                hasVoted = _.find(AssignmentPollBallot.getAll(), function (apb) {
                    return apb.delegate_id === operator.user.id &&
                        apb.poll_id === av.assignment_poll_id;
                });
            }
            if (hasVoted) {
                Messaging.deleteMessage(messageId);
                oldHasVoted = true;
                return;
            }

            if (oldMotionPollId == av.motion_poll_id &&
                oldAssignmentPollId == av.assignment_poll_id &&
                oldIncluded == included &&
                oldHasVoted == hasVoted) {
                return;
            }

            oldIncluded = included;
            oldHasVoted = hasVoted;
            oldMotionPollId = av.motion_poll_id;
            oldAssignmentPollId = av.assignment_poll_id;

            // something has changed. Either the user was added to the voting
            // or one poll has changed. Display a notification!
            if (av.type == 'named_electronic') {
                var msg = gettextCatalog.getString('Vote now!');
                if (av.motion_poll_id) {
                    msg += '<a class="spacer-left" href="/motionpoll/submit/' +
                        av.motion_poll_id + '">' + av.motionPoll.motion.getTitle() + '</a>';
                } else {
                    msg += '<a class="spacer-left" href="/assignmentpoll/submit/' +
                        av.assignment_poll_id + '">' + av.assignmentPoll.assignment.getTitle() + '</a>';
                }

                messageId = Messaging.createOrEditMessage(messageId, msg, 'success', {});
            }
        };

        operator.registerSetUserCallback(function (user) {
            $rootScope.$watch(function () {
                return AuthorizedVoters.lastModified();
            }, updateMessage);
        });

        $rootScope.$watch(function () {
            return MotionPollBallot.lastModified();
        }, updateMessage);

        $rootScope.$watch(function () {
            return AssignmentPollBallot.lastModified();
        }, updateMessage);

        return {
            // Returns the motion poll id, if one poll is active for this motion
            // and the user is authorized. undefined else.
            motionPollIdForMotion: function (motion) {
                if (!av || !motion || !av.motionPoll || motion.id !== av.motionPoll.motion.id) {
                    return;
                }
                if (_.includes(_.keys(av.authorized_voters), operator.user.id.toString())) {
                    return av.motion_poll_id;
                }
            },
            // Returns Y, N or A for an active poll from the motion. If the oerator
            // hasn't voted yet or there is no active poll, false is returned.
            motionPollVoteForMotion: function (motion) {
                var pollId = this.motionPollIdForMotion(motion);
                if (!pollId) {
                    return false;
                }
                var mpb = _.find(MotionPollBallot.getAll(), function (mpb) {
                    return mpb.delegate_id === operator.user.id &&
                        mpb.poll_id === pollId;
                });
                if (mpb) {
                    return mpb.vote;
                }
                return false;
            },
            // Returns the assignment poll id, if one poll is active for the given
            // assignment and the user is authorized to vote. undefined else.
            assignmentPollIdForAssignment: function (assignment) {
                if (!av || !assignment || !av.assignmentPoll || assignment.id !== av.assignmentPoll.assignment.id) {
                    return;
                }
                if (_.includes(_.keys(av.authorized_voters), operator.user.id.toString())) {
                    return av.assignmnt_poll_id;
                }
            },
        };
    }
])

.controller('PollCreateCtrl', [
    '$scope',
    '$http',
    'DS',
    'PollCreateForm',
    'MotionPollType',
    'AssignmentPollType',
    'Assignment',
    'Config',
    'objId',
    'resourceName',
    'onSuccess',
    'onError',
    'ErrorMessage',
    function ($scope, $http, DS, PollCreateForm, MotionPollType, AssignmentPollType,
        Assignment, Config, objId, resourceName, onSuccess, onError, ErrorMessage) {
        $scope.obj = DS.get(resourceName, objId);
        $scope.model = {
            votingType: Config.get('voting_default_voting_type').value,
        };
        $scope.formFields = PollCreateForm.getFormFields();

        $scope.select = function (model) {
            if (resourceName === 'motions/motion') {
                $http.post('/rest/motions/motion/' + objId + '/create_poll/', {}).then(function (success) {
                    MotionPollType.create({
                        poll_id: success.data.createdPollId,
                        type: model.votingType,
                    }).then (function () {
                        $scope.closeThisDialog();
                        if (typeof onSuccess === 'function') {
                            onSuccess(success.data.createdPollId);
                        }
                    }, function (error) {
                        $scope.alert = ErrorMessage.forAlert(error);
                    });
                }, function (error) {
                    $scope.closeThisDialog();
                    if (typeof onError === 'function') {
                        onError(error);
                    }
                });
            } else if (resourceName === 'assignments/assignment') {
                $http.post('/rest/assignments/assignment/' + objId + '/create_poll/', {}).then(function (success) {
                    // $scope.obj is our assignment
                    if ($scope.obj.phase === 0) {
                        $scope.obj.phase = 1;
                        Assignment.save($scope.obj);
                    }

                    AssignmentPollType.create({
                        poll_id: success.data.createdPollId,
                        type: model.votingType,
                    }).then (function () {
                        $scope.closeThisDialog();
                        if (typeof onSuccess === 'function') {
                            onSuccess(success.data.createdPollId);
                        }
                    }, function (error) {
                        $scope.alert = ErrorMessage.forAlert(error);
                    });
                }, function (error) {
                    $scope.closeThisDialog();
                    if (typeof onError === 'function') {
                        onError(error);
                    }
                });
            } else {
                throw "not supported: " + resourceName;
            }
        };
    }
])

.controller('UserListExtraContentCtrl', [
    '$scope',
    'Delegate',
    'User',
    'Keypad',
    'VotingProxy',
    'ErrorMessage',
    'Motion',
    function ($scope, Delegate, User, Keypad, VotingProxy, ErrorMessage) {
        $scope.d = Delegate;

        var $mainScope = $scope.$parent.$parent;
        $mainScope.updateUsers = function () {
            _.forEach($scope.users, function (user) {
                if (Delegate.isDelegate(user)) {
                    user.keypad = Delegate.getKeypad(user.id);
                    if (user.keypad) {
                        user.keypad.newNumber = user.keypad.number;
                    }
                    user.proxy = Delegate.getProxy(user.id);
                }
            });
            $scope.updateTableStats();
        };
        $scope.$watch(function () {
            return Keypad.lastModified();
        }, $mainScope.updateUsers);

        $scope.saveKeypad = function (user) {
            if (user.keypad) {
                var number;
                if (user.keypad.newNumber) {
                    number = parseInt(user.keypad.newNumber);
                    if (isNaN(number) || number <= 0) {
                        return;
                    }
                }
                Delegate.updateKeypad(user, number).then(null, function (error) {
                    $mainScope.alert = ErrorMessage.forAlert(error);
                });
            }
        };

    }
])

.controller('DelegateUpdateCtrl', [
    '$scope',
    '$q',
    '$http',
    'DelegateForm',
    'Delegate',
    'User',
    'ErrorMessage',
    function ($scope, $q, $http, DelegateForm, Delegate, User, ErrorMessage) {
        $scope.model.keypad_number = $scope.model.keypad ? $scope.model.keypad.number : null;
        $scope.model.proxy_id = $scope.model.proxy ? $scope.model.proxy.proxy_id : null;
        $scope.model.mandates_id = Delegate.getMandatesIds($scope.model);
        $scope.model.shares = Delegate.getShares($scope.model);
        $scope.delegateFormFields = DelegateForm.getFormFields($scope.model);

        $scope.delegateSave = function (delegate) {
            var message = '';

            // Check for circular proxy reference.
            if (delegate.mandates_id.indexOf(delegate.proxy_id) >= 0) {
                // TODO (Jochen): Find a translation for this
                message = User.get(delegate.proxy_id).full_name + ' ' +
                    gettextCatalog.getString('cannot be gleichzeitig Vertreter und Vollmachtgeber sein.');
                $scope.$parent.alert = {type: 'danger', msg: message, show: true};
                return;
            }

            // Update keypad, proxy, mandates, voting shares, user.is_present and collect their promises.
            var promises = _.filter([
                Delegate.updateKeypad(delegate, delegate.keypad_number),
                Delegate.updateProxy(delegate, delegate.proxy_id),
            ]);
            promises = promises.concat(Delegate.updateShares(delegate));
            promises = promises.concat(Delegate.updateMandates(delegate));

            // Wait until all promises have been resolved before closing dialog.
            $q.all(promises).then(function () {
                $scope.save(delegate); // call the original save method

                // Get an attendance update.
                // The server will create an attendance log entry if attendance
                // has changed due to keypad, proxy, user present updates issued above.
                $http.get('/voting/attendance/shares/');
            }, function (error) {
                $scope.$parent.alert = ErrorMessage.forAlert(error);
            });
        };
    }
])

.controller('TokensCtrl', [
    '$scope',
    '$http',
    'VotingToken',
    'TokenContentProvider',
    'TokenDocumentProvider',
    'PdfCreate',
    'gettextCatalog',
    'ErrorMessage',
    function ($scope, $http, VotingToken, TokenContentProvider, TokenDocumentProvider,
        PdfCreate, gettextCatalog, ErrorMessage) {
        VotingToken.bindAll({}, $scope, 'tokens');

        $scope.scan = function () {
            $scope.tokenInputDisabled = true;
            var token = $scope.tokenInput;
            VotingToken.create({
                token: token,
            }).then(function (success) {
                $scope.alert = {
                    msg: gettextCatalog.getString('Token') + ' ' + token + ' ' +
                        gettextCatalog.getString('was activated successfully'),
                    type: 'success',
                    show: true,
                };
            }, function (error) {
                $scope.alert = ErrorMessage.forAlert(error);
            });
            $scope.tokenInput = '';
            $scope.tokenInputDisabled = false;
        };

        $scope.generate = function (n) {
            n = parseInt(n)
            if (isNaN(n)) {
                return;
            }
            if (n < 1) {
                n = 1;
            } else if (n > 4096) {
                n = 4096;
            }
            $http.post('/rest/openslides_voting/voting-token/generate/', {N: n}).then(function (success) {
                var filename = gettextCatalog.getString('Tokens') + '.pdf';
                var contentProvider = TokenContentProvider.createInstance(success.data);
                var documentProvider = TokenDocumentProvider.createInstance(contentProvider);
                PdfCreate.download(documentProvider, filename);
            });
        };
    }
])

.controller('AttendanceCtrl', [
    '$scope',
    '$http',
    '$interval',
    'gettextCatalog',
    'VotingPrinciple',
    'AttendanceLog',
    'AttendanceHistoryContentProvider',
    'PdfMakeDocumentProvider',
    'PdfCreate',
    function ($scope, $http, $interval, gettextCatalog, VotingPrinciple,
              AttendanceLog, AttendanceHistoryContentProvider,
              PdfMakeDocumentProvider, PdfCreate) {
        VotingPrinciple.bindAll({}, $scope, 'principles');
        AttendanceLog.bindAll({}, $scope, 'attendanceLogs');

        // Update attendance view whenever attendance logs or voting principles have changed.
        $scope.$watch(function () {
            return AttendanceLog.lastModified() + VotingPrinciple.lastModified();
        }, function () {
            // Get attendance data from server.
            $http.get('/voting/attendance/shares/').then(function (success) {
                $scope.attendance = success.data;
            });
        });

        // Delete all attendance logs.
        $scope.deleteHistory = function () {
            $http.post('/rest/openslides_voting/attendance-log/clear/', {});
        };

        // PDF export
        $scope.pdfExport = function () {
            var filename = gettextCatalog.getString('AttendanceHistory') + '.pdf';
            var contentProvider = AttendanceHistoryContentProvider.createInstance();
            PdfMakeDocumentProvider.createInstance(contentProvider).then(function (documentProvider) {
                PdfCreate.download(documentProvider, filename);
            });
        };
    }
])

.factory('PrincipleForm', [
        'gettextCatalog',
        'Motion',
        'Assignment',
        'VotingPrinciple',
        function (gettextCatalog, Motion, Assignment, VotingPrinciple) {
            return {
                getDialog: function (principle) {
                    return {
                        template: 'static/templates/openslides_voting/principle-form.html',
                        controller: principle ? 'PrincipleUpdateCtrl' : 'PrincipleCreateCtrl',
                        className: 'ngdialog-theme-default wide-form',
                        closeByEscape: false,
                        closeByDocument: false,
                        resolve: {
                            principleId: function () {
                                return principle ? principle.id : void 0;
                            }
                        }
                    };
                },
                getFormFields: function (principle) {
                    var principles = VotingPrinciple.filter({
                        where: {
                            id: {'!=': principle ? principle.id : void 0}
                        }
                    });
                    var freeMotions = _.filter(Motion.getAll(), function (motion) {
                        return !_.some(principles, function (principle) {
                            return _.includes(principle.motions_id, motion.id);
                        });
                    });
                    var freeAssignments = _.filter(Assignment.getAll(), function (assignment) {
                        return !_.some(principles, function (principle) {
                            return _.includes(principle.assignments_id, assignment.id);
                        });
                    });
                    return [
                    {
                        key: 'name',
                        type: 'input',
                        templateOptions: {
                            label: gettextCatalog.getString('Name'),
                            required: true,
                        },
                    },
                    {
                        key: 'decimal_places',
                        type: 'input',
                        templateOptions: {
                            label: gettextCatalog.getString('Decimal places'),
                            type: 'number',
                            required: true,
                            min: 0,
                            max: 6,
                    },
                },
                {
                    key: 'motions_id',
                    type: 'select-multiple',
                    templateOptions: {
                        label: gettextCatalog.getString('Motions'),
                        options: freeMotions,
                        ngOptions: 'option.id as option.getTitle() for option in to.options',
                        placeholder: '(' + gettextCatalog.getString('No motions') + ')',
                    },
                },
                {
                    key: 'assignments_id',
                    type: 'select-multiple',
                    templateOptions: {
                        label: gettextCatalog.getString('Elections'),
                        options: freeAssignments,
                        ngOptions: 'option.id as option.title for option in to.options',
                        placeholder: '(' + gettextCatalog.getString('No elections') + ')',
                    },
                }
                ];
            },
        };
    }
])

.controller('PrincipleCreateCtrl', [
    '$scope',
    'VotingPrinciple',
    'PrincipleForm',
    'ErrorMessage',
    function ($scope, VotingPrinciple, PrincipleForm, ErrorMessage) {
        $scope.model = {
            motions_id: [],
            assignments_id: [],
        };
        $scope.formFields = PrincipleForm.getFormFields();

        // Create principle
        $scope.save = function (principle) {
            VotingPrinciple.create(principle).then(
                function (success) {
                    $scope.closeThisDialog();
                },
                function (error) {
                    $scope.alert = ErrorMessage.forAlert(error);
                }
            );
        };
    }
])

.controller('PrincipleUpdateCtrl', [
    '$scope',
    'VotingPrinciple',
    'PrincipleForm',
    'principleId',
    'ErrorMessage',
    function ($scope, VotingPrinciple, PrincipleForm, principleId, ErrorMessage) {
        $scope.model = angular.copy(VotingPrinciple.get(principleId));
        $scope.formFields = PrincipleForm.getFormFields($scope.model);

        // Save principle
        $scope.save = function (principle) {
            // Inject the changed principle (copy) object back into DS store.
            VotingPrinciple.inject(principle);
            // Save changed keypad object on server side.
            VotingPrinciple.save(principle).then(
                function (success) {
                    $scope.closeThisDialog();
                },
                function (error) {
                    // Save error: revert all changes by restoring original principle object
                    // from server.
                    VotingPrinciple.refresh(principle);
                    $scope.alert = ErrorMessage.forAlert(error);
                }
            );
        };
    }
])

.controller('SharesListCtrl', [
    '$scope',
    '$filter',
    'User',
    'VotingPrinciple',
    'VotingShare',
    'Delegate',
    'PrincipleForm',
    'ngDialog',
    function ($scope, $filter, User, VotingPrinciple, VotingShare, Delegate, PrincipleForm,
        ngDialog) {
        $scope.$watch(function () {
            return User.lastModified();
        }, function () {
            $scope.delegates = Delegate.getDelegates();
        });

        $scope.$watch(function () {
            return VotingShare.lastModified();
        }, function () {
            $scope.shares = VotingShare.getAll();
            _.forEach($scope.shares, function (share) {
                share.newShares = share.shares;
            });
        });

        $scope.$watch(function () {
            return VotingPrinciple.lastModified();
        }, function () {
            $scope.principles = $filter('orderBy')(VotingPrinciple.getAll(), 'id');
        });

        $scope.getShare = function (delegate, principle) {
            return _.find($scope.shares, function (share) {
                return share.delegate_id === delegate.id && share.principle_id === principle.id;
            });
        };

        $scope.saveShare = function (newShares, delegate, principle) {
            var share = $scope.getShare(delegate, principle);
            Delegate.updateShare(delegate, share, newShares, principle.id);
        };

        $scope.openDialog = function (principle) {
            ngDialog.open(PrincipleForm.getDialog(principle));
        };

        $scope.delete = function (principle) {
            VotingPrinciple.destroy(principle);
        };
    }
])

.controller('SharesImportCtrl', [
    '$scope',
    '$q',
    'gettext',
    'VotingPrinciple',
    'VotingShare',
    'User',
    function ($scope, $q, gettext, VotingPrinciple, VotingShare, User) {
        // Set up pagination.
        $scope.pg = {
            firstItem: 0,
            currentPage: 1,
            itemsPerPage: 100,
            pageChanged: function () {
                $scope.pg.firstItem = ($scope.pg.currentPage - 1) * $scope.pg.itemsPerPage;
            }
        };

        // Configure csv.
        var fields = [];
        $scope.principles = [];
        $scope.delegateShares = [];
        $scope.csvConfig = {
            accept: '.csv, .txt',
            encodingOptions: ['UTF-8', 'ISO-8859-1'],
            parseConfig: {
                skipEmptyLines: true
            }
        };

        // Load csv file.
        $scope.onCsvChange = function (csv) {
            var records = [],
                users = User.getAll();

            $scope.clear();

            // Get voting principles and fields from header row.
            if (csv.meta !== undefined) {
                $scope.principles = csv.meta.fields.splice(3);
            }

            // Define field names.
            fields = ['first_name', 'last_name', 'number'].concat($scope.principles);

            // Read csv rows.
            _.forEach(csv.data, function (row) {
                if (row.length >= 4) {
                    var filledRow = _.zipObject(fields, row);
                    records.push(filledRow);
                }
            });
            // Validate each record.
            _.forEach(records, function (record) {
                record.selected = true;
                if (record.first_name == '' && record.last_name == '') {
                    // User is anonymous.
                    record.user_id = null;
                }
                else {
                    // Find user.
                    record.error = {};
                    record.fullname = [record.first_name, record.last_name, record.number].join(' ');
                    var user = _.find(users, function (item) {
                        item.fullname = [item.first_name, item.last_name, item.number].join(' ');
                        return item.fullname == record.fullname;
                    });
                    if (user != undefined) {
                        record.user_id = user.id;
                        record.fullname = user.get_full_name();
                    }
                    else {
                        record.user_id = -1;
                        record.importerror = true;
                        record.error.user = gettext('Error: Participant not found.');
                    }
                }
                // Validate voting shares.
                _.forEach($scope.principles, function (principle) {
                    var num = parseFloat(record[principle]);
                    if (isNaN(num) || num < 0) {
                        record.importerror = true;
                        record.error[principle] = gettext('Error: Not a valid number.');
                    }
                    else {
                        record[principle] = num;
                    }
                });
                $scope.delegateShares.push(record);
            });
            $scope.calcStats();
        };

        $scope.calcStats = function () {
            $scope.sharesWillNotBeImported = 0;
            $scope.sharesWillBeImported = 0;

            $scope.delegateShares.forEach(function (item) {
                if (!item.importerror && item.selected) {
                    $scope.sharesWillBeImported++;
                } else {
                    $scope.sharesWillNotBeImported++;
                }
            });
        };

        // Import voting shares.
        $scope.import = function () {
            var principlesMap = {},
                promises = [];
            $scope.csvImporting = true;

            // Create principles if they do not exist.
            _.forEach($scope.principles, function (principle) {
                var principles = VotingPrinciples.filter({name: principle});
                if (principles.length >= 1) {
                    principlesMap[principle] = principles[0].id;
                }
                else {
                    promises.push(VotingPrinciple.create({
                        name: principle,
                        decimal_places: 6,
                    }).then(function (success) {
                        principlesMap[success.name] = success.id;
                    }));
                }
            });

            $q.all(promises).then(function () {
                _.forEach($scope.delegateShares, function (delegateShare) {
                    if (delegateShare.selected && !delegateShare.importerror) {
                        _.forEach($scope.principles, function (principle) {
                            // Look for an existing voting share.
                            var shares = VotingShare.filter({
                                delegate_id: delegateShare.user_id,
                                principle_id: principleMap[principle],
                            });
                            if (shares.length == 1) {
                                // Update voting share.
                                var share = shares[0];
                                share.shares = delegateShare[principle];
                                VotingShare.save(share).then(function (success) {
                                    delegateShare.imported = true;
                                });
                            }else {
                                // Create voting share.
                                VotingShare.create({
                                    delegate_id: delegateShare.user_id,
                                    principle_id: principleMap[principle],
                                    shares: delegateShare[principle],
                                }).then(function (success) {
                                    delegateShare.imported = true;
                                });
                            }
                        });
                    }
                });
            });
            $scope.csvImported = true;
        };

        // Clear csv import preview.
        $scope.clear = function () {
            $scope.delegateShares = [];
            $scope.csvImporting = false;
            $scope.csvImported = false;
        };
    }
])

.controller('MotionPollVoteDetailCtrl', [
    '$scope',
    '$stateParams',
    '$http',
    'gettextCatalog',
    'Motion',
    'MotionPoll',
    'MotionPollBallot',
    'MotionPollType',
    'VotingPrinciple',
    'VotingShare',
    'osTableFilter',
    'osTableSort',
    'osTablePagination',
    'MotionPollContentProvider',
    'PdfMakeDocumentProvider',
    'PdfCreate',
    function ($scope, $stateParams, $http, gettextCatalog, Motion, MotionPoll,
        MotionPollBallot, MotionPollType, VotingPrinciple, VotingShare, osTableFilter,
        osTableSort, osTablePagination, MotionPollContentProvider, PdfMakeDocumentProvider,
        PdfCreate) {

        var pollId = $stateParams.id;
        var motion = MotionPoll.get(pollId).motion;
        MotionPoll.bindOne(pollId, $scope, 'poll');
        $scope.$watch(function () {
            return Motion.lastModified(motion.id);
        }, function () {
            $scope.motion = Motion.get(motion.id);
            var principles = VotingPrinciple.filter({motions_id: motion.id});
            if (principles.length > 0) {
                $scope.principle = principles[0];
            } else {
                $scope.principle = void 0;
            }
            reloadMotionPollBallots();
        });
        $scope.$watch(function () {
            return MotionPollBallot.lastModified();
        }, reloadMotionPollBallots);

        // Just show all users, that have shares.
        var reloadMotionPollBallots = function () {
            var mpbs = MotionPollBallot.filter({poll_id: pollId});
            if ($scope.principle) {
                $scope.ballots = _.filter(mpbs, function (mpb) {
                    if (!mpb.user) {
                        return true;
                    }
                    var shares = VotingShare.filter({
                        principle_id: $scope.principle.id,
                        delegate_id: mpb.user.id
                    });
                    return shares.length > 0 && shares[0].shares > 0;
                });
            } else {
                $scope.ballots = mpbs;
            }
        }

        // Get poll type for motion
        var pollTypes = MotionPollType.filter({poll_id: pollId});
        $scope.pollType = pollTypes.length >= 1 ? pollTypes[0].type : 'analog';

        // Handle table column sorting.
        $scope.filter = osTableFilter.createInstance('MotionPollDetailFilter');
        $scope.filter.propertyFunctionList = [
            function (ballot) { return ballot.getVote(); },
            function (ballot) { return ballot.user ? ballot.user.full_name : ''; },
            function (ballot) { return ballot.result_token !== 0 ? ballot.result_token : ''; }
        ];

        $scope.sort = osTableSort.createInstance('MotionPollDetailSort');
        if (!$scope.sort.column) {
            if ($scope.pollType === 'token_based_electronic') {
                $scope.sort.column = 'result_token';
            } else {
                $scope.sort.column = 'user.full_name';
            }
        }

        $scope.pagination = osTablePagination.createInstance('MotionPollDetailPagination');

        // PDF export
        $scope.pdfExport = function () {
            var filename = gettextCatalog.getString('Motion') + ' ';
            if ($scope.motion.identifier) {
                filename += $scope.motion.identifier;
            } else {
                filename += $scope.motion.getTitle();
            }
            filename += ' ' + gettextCatalog.getString('SingleVotes') + '.pdf';
            var contentProvider = MotionPollContentProvider.createInstance(
                $scope.motion, $scope.poll, $scope.ballotsFiltered, $scope.pollType);
            PdfMakeDocumentProvider.createInstance(contentProvider).then(function (documentProvider) {
                PdfCreate.download(documentProvider, filename);
            });
        };

        $scope.anonymizeVotes = function () {
            $http.post('/rest/openslides_voting/motion-poll-ballot/pseudoanonymize_votes/', {poll_id: pollId});
        };
    }
])

.factory('KeypadForm', [
    'gettextCatalog',
    'User',
    function (gettextCatalog, User) {
        return {
            getDialog: function (keypad) {
                var resolve = {};
                if (keypad) {
                    resolve = {
                        keypad: function () {
                            return keypad;
                        },
                    };
                }
                return {
                    template: 'static/templates/openslides_voting/keypad-form.html',
                    controller: (keypad) ? 'KeypadUpdateCtrl' : 'KeypadCreateCtrl',
                    className: 'ngdialog-theme-default',
                    closeByEscape: false,
                    closeByDocument: false,
                    resolve: (resolve) ? resolve : null,
                };
            },
            getFormFields: function () {
                return [
                {
                    key: 'number',
                    type: 'input',
                    templateOptions: {
                        label: gettextCatalog.getString('Keypad number'),
                        type: 'number',
                        required: true,
                    },
                },
                {
                    key: 'user_id',
                    type: 'select-single',
                    templateOptions: {
                        label: gettextCatalog.getString('Participant'),
                        options: _.orderBy(User.getAll(), 'full_name'),
                        ngOptions: 'option.id as option.full_name for option in to.options',
                        placeholder: '(' + gettextCatalog.getString('Anonymous') + ')',
                    },
                }
                ];
            }
        };
    }
])

.controller('KeypadListCtrl', [
    '$scope',
    '$http',
    '$timeout',
    'ngDialog',
    'KeypadForm',
    'Keypad',
    'User',
    'VotingController',
    'ErrorMessage',
    function ($scope, $http, $timeout, ngDialog, KeypadForm, Keypad, User, VotingController, ErrorMessage) {
        //Keypad.bindAll({}, $scope, 'keypads');
        // User.bindAll({}, $scope, 'users');
        VotingController.bindOne(1, $scope, 'vc');
        $scope.alert = {};

        $scope.$watch(function () {
            return Keypad.lastModified() + User.lastModified();
        }, function () {
            _.forEach(Keypad.getAll(), function (keypad) {
                keypad.active = keypad.isActive();
                keypad.identified = keypad.isIdentified();
            });
            $scope.keypads = Keypad.getAll();
        });

        // Set up pagination.
        $scope.pg = {
            'firstItem': 0,
            'currentPage': 1,
            'itemsPerPage': 50,
            'pageChanged': function () {
                $scope.pg.firstItem = ($scope.pg.currentPage - 1) * $scope.pg.itemsPerPage;
            }
        };

        // Handle table column sorting.
        $scope.sortColumn = 'number';
        $scope.reverse = false;
        $scope.toggleSort = function ( column ) {
            if ( $scope.sortColumn === column ) {
                $scope.reverse = !$scope.reverse;
            }
            $scope.sortColumn = column;
        };

        // Define custom search filter string.
        $scope.getFilterString = function (keypad) {
            var user = '';
            if (keypad.user) {
                user = keypad.user.get_full_name();
            }
            return [
                keypad.number,
                user
            ].join(' ');
        };

        // Open new/edit dialog.
        $scope.openDialog = function (keypad) {
            ngDialog.open(KeypadForm.getDialog(keypad));
        };

        // Delete functions.
        $scope.isDeleteMode = false;
        $scope.checkAll = function () {
            angular.forEach($scope.keypads, function (keypad) {
                keypad.selected = $scope.selectedAll;
            });
        };
        $scope.uncheckAll = function () {
            if (!$scope.isDeleteMode) {
                $scope.selectedAll = false;
                angular.forEach($scope.keypads, function (keypad) {
                    keypad.selected = false;
                });
            }
        };
        $scope.deleteMultiple = function () {
            // Delete selected keypads.
            angular.forEach($scope.keypads, function (keypad) {
                if (keypad.selected)
                    Keypad.destroy(keypad.id);
            });
            $scope.isDeleteMode = false;
            $scope.uncheckAll();
        };
        $scope.delete = function (keypad) {
            // Delete single keypad.
            Keypad.destroy(keypad.id);
        };

        // Keypad system test.
        $scope.startSystemTest = function () {
            $scope.device = null;

            _.forEach($scope.keypads, function (keypad) {
                keypad.in_range = false;
                keypad.battery_level = -1;
            });

            // Get votecollector device status.
            $http.post('/rest/openslides_voting/voting-controller/1/update_votecollector_device_status/').then(
                function (success) {
                    $scope.device = success.data.device;
                    if (success.data.connected) {
                        // Ping votecollector keypads.
                        $http.post('/rest/openslides_voting/voting-controller/1/ping_votecollector/').then(
                            function (success) {
                                // Stop pinging after 30 seconds if still running.
                                $timeout(function () {
                                    if ($scope.vc.is_voting && $scope.vc.voting_mode === 'ping') {
                                        $scope.stopSystemTest();
                                    }
                                }, 30000);
                            },
                            function (error) {
                                $scope.device = ErrorMessage.forAlert(error).msg;
                            }
                        );
                    }
                },
                function (error) {
                    $scope.device = ErrorMessage.forAlert(error).msg;
                }
            );
        };

        $scope.stopSystemTest = function () {
            $http.post('/rest/openslides_voting/voting-controller/1/stop/');
        };
    }
])

.controller('KeypadCreateCtrl', [
    '$scope',
    'Keypad',
    'KeypadForm',
    'ErrorMessage',
    function ($scope, Keypad, KeypadForm, ErrorMessage) {
        $scope.alert = {};
        $scope.model = {};
        $scope.formFields = KeypadForm.getFormFields();

        // Save keypad.
        $scope.save = function (keypad) {
            // Create a new keypad.
            Keypad.create(keypad).then(function (success) {
                $scope.closeThisDialog();
            }, function (error) {
                $scope.alert = ErrorMessage.forAlert(error);
            });
        };
    }
])

.controller('KeypadUpdateCtrl', [
    '$scope',
    'Keypad',
    'KeypadForm',
    'keypad',
    function ($scope, Keypad, KeypadForm, keypad) {
        // Use a deep copy of keypad object so list view is not updated while editing the form.
        $scope.model = angular.copy(keypad);
        $scope.formFields = KeypadForm.getFormFields();

        // Save keypad.
        $scope.save = function (keypad) {
            // Inject the changed keypad (copy) object back into DS store.
            Keypad.inject(keypad);
            // Save changed keypad object on server side.
            Keypad.save(keypad).then(
                function (success) {
                    $scope.closeThisDialog();
                },
                function (error) {
                    // Save error: revert all changes by restoring original keypad object
                    // from server.
                    Keypad.refresh(keypad);
                    var message = '';
                    for (var e in error.data) {
                        message += e + ': ' + error.data[e] + ' ';
                    }
                    $scope.alert = {type: 'danger', msg: message, show: true};
                }
            );
        };
    }
])

.controller('KeypadImportCtrl', [
    '$scope',
    'gettext',
    'Keypad',
    'User',
    function ($scope, gettext, Keypad, User) {
        // Set up pagination.
        // http://stackoverflow.com/questions/34775157/angular-ui-bootstrap-pagination-ng-model-not-updating
        // http://stackoverflow.com/questions/33181191/scope-currentpage-not-updating-angular-ui-pagination
        $scope.pg = {
            'firstItem': 0,
            'currentPage': 1,
            'itemsPerPage': 100,
            'pageChanged': function () {
                $scope.pg.firstItem = ($scope.pg.currentPage - 1) * $scope.pg.itemsPerPage;
            }
        };

        // Configure csv.
        $scope.csvConfig = {
            accept: '.csv, .txt',
            encodingOptions: ['UTF-8', 'ISO-8859-1'],
            parseConfig: {
                skipEmptyLines: true
            }
        };

        // Load csv file.
        var FIELDS = ['first_name', 'last_name', 'number', 'keypad'];
        $scope.users = [];
        $scope.onCsvChange = function (csv) {
            var users = User.getAll(),
                records = [];

            $scope.clear();

            // Read csv rows.
            _.forEach(csv.data, function (row) {
                if (row.length >= 4) {
                    var filledRow = _.zipObject(FIELDS, row);
                    records.push(filledRow);
                }
            });
            // Validate each record.
            _.forEach(records, function (record) {
                record.selected = true;
                if (record.first_name == '' && record.last_name == '') {
                    // User is anonymous.
                    record.user_id = null;
                }
                else {
                    // Find user.
                    record.fullname = [record.first_name, record.last_name, record.number].join(' ');
                    var user = _.find(users, function (item) {
                        item.fullname = [item.first_name, item.last_name, item.number].join(' ');
                        return item.fullname == record.fullname;
                    });
                    if (user != undefined) {
                        record.user_id = user.id;
                        record.fullname = user.get_full_name();
                    }
                    else {
                        record.user_id = -1;
                        record.importerror = true;
                        record.user_error = gettext('Error: Participant not found.');
                    }
                }
                // Validate keypad number.
                var num = parseInt(record.keypad);
                if (isNaN(num) || num <= 0) {
                    record.importerror = true;
                    record.keypad_error = gettext('Error: Keypad number must be a positive integer value.');
                }
                else {
                    record.keypad = num;
                    if (Keypad.filter({ 'number': record.keypad }).length > 0) {
                        record.importerror = true;
                        record.keypad_error = gettext('Error: Keypad number already exists.');
                    }
                }
                $scope.users.push(record);
            });
            $scope.calcStats();
        };

        $scope.calcStats = function () {
            $scope.keypadsWillNotBeImported = 0;
            $scope.keypadsWillBeImported = 0;

            $scope.users.forEach(function (item) {
                if (!item.importerror && item.selected) {
                    $scope.keypadsWillBeImported++;
                } else {
                    $scope.keypadsWillNotBeImported++;
                }
            });
        };

        // Import keypads.
        $scope.import = function () {
            $scope.csvImporting = true;
            angular.forEach($scope.users, function (user) {
                if (user.selected && !user.importerror) {
                    // Create keypad.
                    Keypad.create({'number': user.keypad, 'user_id': user.user_id}).then(
                        function(success) {
                            user.imported = true;
                        }
                    );
                }
            });
            $scope.csvImported = true;
        };

        // Clear csv import preview.
        $scope.clear = function () {
            $scope.users = [];
            $scope.csvImporting = false;
            $scope.csvImported = false;
        };
    }
])

.factory('AbsenteeVoteForm', [
    'gettextCatalog',
    'Delegate',
    'Motion',
    'Assignment',
    function (gettextCatalog, Delegate, Motion, Assignment) {
        return {
            getDialog: function (absenteeVote) {
                return {
                    template: 'static/templates/openslides_voting/absentee-vote-form.html',
                    controller: (absenteeVote) ? 'AbsenteeVoteUpdateCtrl' : 'AbsenteeVoteCreateCtrl',
                    className: 'ngdialog-theme-default',
                    closeByEscape: false,
                    closeByDocument: false,
                    resolve: {
                        absenteeVote: function () {
                            return absenteeVote;
                        },
                    },
                };
            },
            getFormFields: function (edit) {
                var voteField = {
                    key: 'vote',
                    type: 'input',
                    templateOptions: {
                        label: gettextCatalog.getString('Voting intention'),
                        required: true,
                        description: gettextCatalog.getString('Please type Y, N or A for YNA-Votings or the candidate number for candidate voting.')
                    },
                };

                if (edit) {
                    return [voteField];
                } else {
                    return [
                    {
                        key: 'delegate_id',
                        type: 'select-single',
                        templateOptions: {
                            label: gettextCatalog.getString('Participant'),
                            options: _.orderBy(Delegate.getDelegates(), 'full_name'),
                            ngOptions: 'option.id as option.full_name for option in to.options',
                            required: true,
                        },
                    },
                    {
                        key: 'motion_id',
                        type: 'select-single',
                        templateOptions: {
                            label: gettextCatalog.getString('Motion'),
                            options: Motion.filter({orderBy: 'identifier'}),
                            ngOptions: 'option.id as option.getAgendaTitle() for option in to.options',
                        },
                        watcher: {
                            listener: function (field, newValue, oldValue, formScope) {
                                if (newValue) {
                                    formScope.model.assignment_id = null;
                                }
                            },
                        },
                    },
                    // TODO: Make absentee votes for assignments possible
                    /*{
                        key: 'assignment_id',
                        type: 'select-single',
                        templateOptions: {
                            label: gettextCatalog.getString('Election'),
                            options: Assignment.filter({orderBy: 'title'}),
                            ngOptions: 'option.id as option.getAgendaTitle() for option in to.options',
                        },
                        watcher: {
                            listener: function (field, newValue, oldValue, formScope) {
                                if (newValue) {
                                    formScope.model.motion_id = null;
                                }
                            },
                        },
                    },*/
                    voteField
                    ];
                }
            }
        };
    }
])

.controller('AbsenteeVoteListCtrl', [
    '$scope',
    'ngDialog',
    'AbsenteeVoteForm',
    'MotionAbsenteeVote',
    'AssignmentAbsenteeVote',
    function ($scope, ngDialog, AbsenteeVoteForm, MotionAbsenteeVote, AssignmentAbsenteeVote) {
        $scope.alert = {};
        $scope.absenteeVotes = [];

        var update = function () {
            $scope.absenteeVotes = [];
            _.forEach(MotionAbsenteeVote.getAll(), function (absenteeVote) {
                $scope.absenteeVotes.push(Object.assign(absenteeVote));
            });
            _.forEach(AssignmentAbsenteeVote.getAll(), function (absenteeVote) {
                $scope.absenteeVotes.push(Object.assign(absenteeVote));
            });
        }

        $scope.$watch(function () {
            return MotionAbsenteeVote.lastModified();
        }, update);
        $scope.$watch(function () {
            return AssignmentAbsenteeVote.lastModified();
        }, update);

        // Set up pagination.
        $scope.pg = {
            'firstItem': 0,
            'currentPage': 1,
            'itemsPerPage': 50,
            'pageChanged': function () {
                $scope.pg.firstItem = ($scope.pg.currentPage - 1) * $scope.pg.itemsPerPage;
            }
        };

        // Handle table column sorting.
        $scope.sortColumn = 'delegate.full_name';
        $scope.reverse = false;
        $scope.toggleSort = function (column) {
            if ($scope.sortColumn === column) {
                $scope.reverse = !$scope.reverse;
            }
            $scope.sortColumn = column;
        };

        // Define custom search filter string.
        $scope.getFilterString = function (absenteeVote) {
            return [
                absenteeVote.delegate.full_name,
                absenteeVote.getObjectTitle(),
                absenteeVote.getVote()
            ].join(' ');
        };

        // Open new/edit dialog.
        $scope.openDialog = function (absenteeVote) {
            ngDialog.open(AbsenteeVoteForm.getDialog(absenteeVote));
        };

        // Delete functions.
        $scope.isDeleteMode = false;
        $scope.checkAll = function () {
            _.forEach($scope.absenteeVotes, function (absenteeVote) {
                absenteeVote.selected = $scope.selectedAll;
            });
        };
        $scope.uncheckAll = function () {
            if (!$scope.isDeleteMode) {
                $scope.selectedAll = false;
                _.forEach($scope.absenteeVotes, function (absenteeVote) {
                    absenteeVote.selected = false;
                });
            }
        };
        $scope.deleteMultiple = function () {
            // Delete selected absentee votes.
            _.forEach($scope.absenteeVotes, function (absenteeVote) {
                if (absenteeVote.selected) {
                    $scope.delete(absenteeVote);
                }
            });
            $scope.isDeleteMode = false;
            $scope.uncheckAll();
        };
        $scope.delete = function (absenteeVote) {
            // Delete single absentee vote.
            if (absenteeVote.motion_id) {
                MotionAbsenteeVote.destroy(absenteeVote.id);
            } else {
                AssignmentAbsenteeVote.destroy(absenteeVote.id);
            }
        };
    }
])

.controller('AbsenteeVoteCreateCtrl', [
    '$scope',
    'MotionAbsenteeVote',
    'AssignmentAbsenteeVote',
    'AbsenteeVoteForm',
    'ErrorMessage',
    function ($scope, MotionAbsenteeVote, AssignmentAbsenteeVote, AbsenteeVoteForm,
        ErrorMessage) {
        $scope.model = {};
        $scope.formFields = AbsenteeVoteForm.getFormFields();

        // Save absentee vote.
        $scope.save = function (absenteeVote) {
            // Create an absentee vote.
            if (absenteeVote.motion_id) {
                MotionAbsenteeVote.create(absenteeVote).then(function (success) {
                    $scope.closeThisDialog();
                },
                function (error) {
                    $scope.alert = ErrorMessage.forAlert(error);
                });
            } else {
                /*AssignmentAbsenteeVote.create(absenteeVote).then(function (success) {
                    $scope.closeThisDialog();
                },
                function (error) {
                    $scope.alert = ErrorMessage.forAlert(error);
                });*/
            }
        };

    }
])

.controller('AbsenteeVoteUpdateCtrl', [
    '$scope',
    'MotionAbsenteeVote',
    'AssignmentAbsenteeVote',
    'AbsenteeVoteForm',
    'absenteeVote',
    'ErrorMessage',
    function ($scope, MotionAbsenteeVote, AssignmentAbsenteeVote, AbsenteeVoteForm,
        absenteeVote, ErrorMessage) {
        // Use a deep copy of absentee vote object so list view is not updated while editing the form.
        $scope.model = angular.copy(absenteeVote);
        $scope.formFields = AbsenteeVoteForm.getFormFields(true); // Just aloow the vote to be edited

        // Save absentee vote.
        $scope.save = function (absenteeVote) {
            if (absenteeVote.motion_id) {
                // Inject the changed absentee vote (copy) object back into DS store.
                MotionAbsenteeVote.inject(absenteeVote);
                MotionAbsenteeVote.save(absenteeVote).then(function (success) {
                    $scope.closeThisDialog();
                },
                function (error) {
                    MotionAbsenteeVote.refresh(absenteeVote);
                    $scope.alert = ErrorMessage.forAlert(error);
                });
            } else {
                // Inject the changed absentee vote (copy) object back into DS store.
                /*AssignmentAbsenteeVote.inject(absenteeVote);
                AssignmentAbsenteeVote.save(absenteeVote).then(function (success) {
                    $scope.closeThisDialog();
                },
                function (error) {
                    AssignmentAbsenteeVote.refresh(absenteeVote);
                    $scope.alert = ErrorMessage.forAlert(error);
                });*/
            }
        };
    }
])

.controller('AbsenteeVoteImportCtrl', [
    '$scope',
    'gettext',
    'MotionAbsenteeVote',
    'AssignmentAbsenteeVote',
    'User',
    'Motion',
    function ($scope, gettext, MotionAbsenteeVote, AssignmentAbsenteeVote, User, Motion) {
        // Set up pagination.
        $scope.pg = {
            'firstItem': 0,
            'currentPage': 1,
            'itemsPerPage': 100,
            'pageChanged': function () {
                $scope.pg.firstItem = ($scope.pg.currentPage - 1) * $scope.pg.itemsPerPage;
            }
        };

        // Configure csv.
        $scope.csvConfig = {
            accept: '.csv, .txt',
            encodingOptions: ['UTF-8', 'ISO-8859-1'],
            parseConfig: {
                skipEmptyLines: true
            }
        };

        // Load csv file.
        var FIELDS = ['first_name', 'last_name', 'number', 'motion_identifier', 'vote'];
        $scope.users = [];
        $scope.delegateVotes = [];
        $scope.onCsvChange = function (csv) {
            var users = User.getAll(),
                motions = Motion.getAll(),
                records = [];

            $scope.clear();

            // Read csv rows.
            _.forEach(csv.data, function (row) {
                if (row.length >= 5) {
                    var filledRow = _.zipObject(FIELDS, row);
                    records.push(filledRow);
                }
            });
            // Validate each record.
            _.forEach(records, function (record) {
                record.selected = true;
                if (record.first_name == '' && record.last_name == '') {
                    // User is anonymous.
                    record.user_id = null;
                }
                else {
                    // Find user.
                    record.fullname = [record.first_name, record.last_name, record.number].join(' ');
                    var user = _.find(users, function (item) {
                        item.fullname = [item.first_name, item.last_name, item.number].join(' ');
                        return item.fullname == record.fullname;
                    });
                    if (user !== undefined) {
                        record.user_id = user.id;
                        record.fullname = user.get_full_name();
                    }
                    else {
                        record.user_id = -1;
                        record.importerror = true;
                        record.user_error = gettext('Error: Participant not found.');
                    }
                }
                // Find motion.
                var motions = Motion.filter({identifier: record.motion_identifier});
                if (motions.length == 1) {
                    record.motion_id = motions[0].id;
                    record.motion = motions[0].identifier + ' - ' + motions[0].getTitle();
                }
                else {
                    record.importerror = true;
                    record.motion_error = gettext('Error: Motion not found.');
                }
                // Validate vote.
                if (['Y', 'N', 'A'].indexOf(record.vote) == -1) {
                    record.importerror = true;
                    record.vote_error = gettext('Error: Vote must be one of Y, N, A.');
                }
                // Temporarily create absentee vote instance to look up vote properties.
                var av = MotionAbsenteeVote.createInstance({vote: record.vote});
                record.vote_name = av.getVote();
                record.vote_icon = av.getVoteIcon();

                $scope.delegateVotes.push(record);
            });
            $scope.calcStats();
        };

        $scope.calcStats = function () {
            $scope.votesWillNotBeImported = 0;
            $scope.votesWillBeImported = 0;

            $scope.delegateVotes.forEach(function (item) {
                if (!item.importerror && item.selected) {
                    $scope.votesWillBeImported++;
                } else {
                    $scope.votesWillNotBeImported++;
                }
            });
        };

        // Import absentee votes.
        $scope.import = function () {
            $scope.csvImporting = true;
            angular.forEach($scope.delegateVotes, function (delegateVote) {
                if (delegateVote.selected && !delegateVote.importerror) {
                    // Look for an existing vote.
                    var avs = MotionAbsenteeVote.filter({
                        delegate_id: delegateVote.user_id,
                        motion_id: delegateVote.motion_id
                    });
                    if (avs.length == 1) {
                        // Update vote.
                        avs[0].vote = delegateVote.vote;
                        Motion.AbsenteeVote.save(avs[0]).then(function (success) {
                            delegateVote.imported = true;
                        });
                    }
                    else {
                        // Create vote.
                        Motion.AbsenteeVote.create({
                            delegate_id: delegateVote.user_id,
                            motion_id: delegateVote.motion_id,
                            vote: delegateVote.vote
                        }).then(function (success) {
                            delegateVote.imported = true;
                        });
                    }
                }
            });
            $scope.csvImported = true;
        };

        // Clear csv import preview.
        $scope.clear = function () {
            $scope.delegateVotes = [];
            $scope.csvImporting = false;
            $scope.csvImported = false;
        };
    }
])

.factory('PollFormVotingCtrlBase', [
    '$http',
    'gettextCatalog',
    'Projector',
    'ProjectHelper',
    'ErrorMessage',
    function ($http, gettextCatalog, Projector, ProjectHelper, ErrorMessage) {
        return {
            populateScope: function ($scope, modelName, modelPollType, projectorName, startUrl, resultsUrl,
                clearUrl) {

                $scope.isAnalogPoll = function () {
                    var pollTypes = modelPollType.filter({poll_id: $scope.poll.id});
                    return pollTypes.length === 0 || pollTypes[0].type === 'analog';
                };

                $scope.canStopVoting = function () {
                    return $scope.vc && $scope.vc.is_voting;
                };

                $scope.isThisPollActive = function () {
                    return $scope.vc && $scope.vc.voting_mode === modelName &&
                        $scope.vc.voting_target === $scope.poll.id;
                };

                $scope.canClearVotes = function () {
                    // If votes were cast and voting is not active for this poll.
                    return $scope.vc && $scope.poll.votescast !== null &&
                        (!$scope.vc.is_voting || $scope.vc.voting_mode !== modelName ||
                        $scope.vc.voting_target !== $scope.poll.id);
                };

                $scope.startVoting = function () {
                    $scope.$parent.$parent.$parent.alert = {};

                    $http.post('/rest/openslides_voting/voting-controller/1/' + startUrl + '/', {
                        poll_id: $scope.poll.id,
                    }).then(null, function (error) {
                        $scope.$parent.$parent.$parent.alert = ErrorMessage.forAlert(error);
                    });
                };

                $scope.stopVoting = function () {
                    $scope.$parent.$parent.$parent.alert = {};

                    var thisPollActive = $scope.isThisPollActive();

                    // Stop votingcontroller.
                    $http.post('/rest/openslides_voting/voting-controller/1/stop/').then(
                        function (success) {
                            if (thisPollActive)  {
                                $http.post('/rest/openslides_voting/voting-controller/1/' + resultsUrl + '/', {
                                    poll_id: $scope.poll.id,
                                }).then($scope.enterResults, function (error) {
                                    $scope.$parent.$parent.$parent.alert = ErrorMessage.forAlert(error);
                                });
                            }
                        },
                        function (error) {
                            $scope.$parent.$parent.$parent.alert = ErrorMessage.forAlert(error);
                        }
                    );
                };

                $scope.clearVotes = function () {
                    $scope.$parent.$parent.$parent.alert = {};
                    $http.post('/rest/openslides_voting/voting-controller/1/' + clearUrl + '/', {
                        poll_id: $scope.poll.id,
                    }).then($scope.clearForm);
                };

                $scope.getDefaultVotingStatus = function () {
                    if ($scope.vc.voting_mode === 'ping') {
                        return gettextCatalog.getString('System test is running.');
                    }
                    if ($scope.vc.voting_mode === 'Item') {
                        return gettextCatalog.getString('Speakers voting is running for agenda item') + ' ' +
                            $scope.vc.voting_target + '.';
                    }
                    if ($scope.vc.voting_mode === 'AssignmentPoll') {
                        return gettextCatalog.getString('An election is running.');
                    }
                    if ($scope.vc.voting_mode === 'MotionPoll') {
                        return gettextCatalog.getString('A motion voting is running.');
                    }
                };

                $scope.projectModel = {
                    project: function (projectorId) {
                        var isProjectedIds = this.isProjected();
                        var requestData = {
                            clear_ids: isProjectedIds,
                        };
                        if (_.indexOf(isProjectedIds, projectorId) === -1) {
                            requestData.prune = {
                                id: projectorId,
                                element: {
                                    name: projectorName,
                                    id: $scope.poll.id,
                                },
                            };
                        }
                        ProjectHelper.project(requestData);
                    },
                    isProjected: function () {
                        var self = this;
                        var predicate = function (element) {
                            return element.name === projectorName &&
                                typeof element.id !== 'undefined' &&
                                element.id === $scope.poll.id;
                        };

                        var isProjectedIds = [];
                        Projector.getAll().forEach(function (projector) {
                            if (typeof _.findKey(projector.elements, predicate) === 'string') {
                                isProjectedIds.push(projector.id);
                            }
                        });
                        return isProjectedIds;
                    },
                };
            },
        };
    }
])

.controller('MotionPollFormVotingCtrl', [
    '$scope',
    '$http',
    'gettextCatalog',
    'MotionPollBallot',
    'MotionPollType',
    'Projector',
    'VotingController',
    'PollFormVotingCtrlBase',
    'ErrorMessage',
    function ($scope, $http, gettextCatalog, MotionPollBallot, MotionPollType, Projector,
        VotingController, PollFormVotingCtrlBase, ErrorMessage) {
        Projector.bindAll({}, $scope, 'projectors');
        VotingController.bindOne(1, $scope, 'vc');

        PollFormVotingCtrlBase.populateScope($scope, 'MotionPoll', MotionPollType, 'voting/motion-poll',
            'start_motion', 'results_motion_votes', 'clear_motion_votes');

        $scope.clearForm = function () {
            $scope.poll.yes = null;
            $scope.poll.no = null;
            $scope.poll.abstain = null;
            $scope.poll.votesvalid = null;
            $scope.poll.votesinvalid = null;
            $scope.poll.votescast = null;
        };

        $scope.canStartVoting = function () {
            return $scope.vc && $scope.poll.votescast === null && !$scope.vc.is_voting;
        };

        $scope.enterResults = function (success) {
            // Store result in DS model; updates form inputs.
            $scope.poll.yes = success.data.Y[1];
            $scope.poll.no = success.data.N[1];
            $scope.poll.abstain = success.data.A[1];
            $scope.poll.votesvalid = success.data.valid[1];
            $scope.poll.votesinvalid = success.data.invalid[1];
            $scope.poll.votescast = success.data.casted[1];

            // Prompt user to save result.
            $scope.$parent.$parent.$parent.alert = {
                type: 'info',
                msg: gettextCatalog.getString('Motion voting has finished.') + ' ' +
                     gettextCatalog.getString('Save this result now!'),
                show: true
            };
        };

        $scope.getVotingStatus = function () {
            if (!$scope.vc || !$scope.vc.is_voting) {
                return '';
            }
            if ($scope.vc.voting_mode === 'MotionPoll') {
                if ($scope.vc.voting_target !== $scope.poll.id) {
                    return gettextCatalog.getString('Another motion voting is running.');
                }
                var msg =  gettextCatalog.getString('Votes received:') + ' ' +
                        $scope.vc.votes_received;
                if ($scope.vc.votes_count > 0) {
                    msg += ' / ' + $scope.vc.votes_count;
                }
                return msg;
            } else {
                return $scope.getDefaultVotingStatus();
            }
        };

    }
])
.controller('AssignmentPollFormVotingCtrl', [
    '$scope',
    '$http',
    'gettextCatalog',
    'Projector',
    'VotingController',
    'AssignmentPollType',
    'AssignmentPollBallot',
    'PollFormVotingCtrlBase',
    'ErrorMessage',
    function ($scope, $http, gettextCatalog, Projector, VotingController, AssignmentPollType,
        AssignmentPollBallot, PollFormVotingCtrlBase, ErrorMessage) {
        Projector.bindAll({}, $scope, 'projectors');
        VotingController.bindOne(1, $scope, 'vc');

        PollFormVotingCtrlBase.populateScope($scope, 'AssignmentPoll', AssignmentPollType,
            'voting/assignment-poll', 'start_assignment', 'results_assignment_votes',
            'clear_assignment_votes');

        $scope.clearForm = function () {
            _.forEach($scope.poll.options, function (option) {
                var id = option.candidate.id;
                $scope.poll['yes_' + id] = null;
                $scope.poll['no_' + id] = null;
                $scope.poll['abstain_' + id] = null;
                $scope.poll['vote_' + id] = null;
            });
            $scope.poll.votesvalid = null;
            $scope.poll.votesinvalid = null;
            $scope.poll.votescast = null;
        };

        $scope.canStartVoting = function () {
            // check for support from votecollector.
            var pollTypes = AssignmentPollType.filter({poll_id: $scope.poll.id});
            var pollType = pollTypes.length >= 1 ? pollTypes[0].type : 'analog_voting';
            var pollTypeIsVc = (pollType === 'votecollector' || pollType === 'votecollector_anonym');
            var vcOk = (!pollTypeIsVc || $scope.poll.pollmethod === 'votes' ||
                ($scope.poll.pollmethod === 'yna' && $scope.poll.options.length === 1));
            return vcOk && $scope.vc && $scope.poll.votescast === null && !$scope.vc.is_voting;
        };

        $scope.enterResults = function (success) {
            _.forEach(success.data, function (value, key) {
                if (key === 'casted') {
                    $scope.poll.votescast = value[0];
                } else if (key === 'valid') {
                    $scope.poll.votesvalid = value[0];
                } else if (key === 'invalid') {
                    $scope.poll.votesinvalid = value[0];
                } else { // a candidate
                    if ($scope.poll.pollmethod === 'votes') {
                        $scope.poll['vote_' + key] = value[1];
                    } else {
                        $scope.poll['yes_' + key] = value.Y[1];
                        $scope.poll['no_' + key] = value.N[1];
                        if ($scope.poll.pollmethod === 'yna') {
                            $scope.poll['abstain_' + key] = value.A[1];
                        }
                    }
                }
            });

            // Prompt user to save result.
            $scope.$parent.$parent.$parent.alert = {
                type: 'info',
                msg: gettextCatalog.getString('Election voting has finished.') + ' ' +
                     gettextCatalog.getString('Save this result now!'),
                show: true
            };
        };

        $scope.getVotingStatus = function () {
            if (!$scope.vc || !$scope.vc.is_voting) {
                return '';
            }
            if ($scope.vc.voting_mode === 'AssignmentPoll') {
                if ($scope.vc.voting_target !== $scope.poll.id) {
                    return gettextCatalog.getString('Another election is running.');
                }
                var msg =  gettextCatalog.getString('Votes received:') + ' ' +
                        $scope.vc.votes_received;
                if ($scope.vc.votes_count > 0) {
                    msg += ' / ' + $scope.vc.votes_count;
                }
                return msg;
            } else {
                return $scope.getDefaultVotingStatus();
            }
        };
    }
])

.controller('SpeakerListCtrl', [
    '$scope',
    '$http',
    'VotingController',
    'ErrorMessage',
    function ($scope, $http, VotingController, ErrorMessage) {
        VotingController.bindOne(1, $scope, 'vc');

        $scope.canStartVoting = function () {
            return $scope.vc && !$scope.vc.is_voting;
        };

        $scope.canStopVoting = function () {
            return $scope.vc && $scope.vc.is_voting;
        };

        $scope.isThisPollActive = function () {
            return $scope.vc && $scope.vc.voting_mode === 'Item' &&
                $scope.vc.voting_target === $scope.item.id;
        };

        $scope.startVoting = function () {
            $scope.$parent.$parent.$parent.alert = {};

            $http.post('/rest/openslides_voting/voting-controller/1/start_speaker_list/', {
                item_id: $scope.item.id,
            }).then(null, function (error) {
                $scope.$parent.$parent.$parent.alert = ErrorMessage.forAlert(error);
            });
        };

        $scope.stopVoting = function () {
            $scope.$parent.$parent.$parent.alert = {};

            $http.post('/rest/openslides_voting/voting-controller/1/stop/').then(null, function (error) {
                $scope.$parent.$parent.$parent.alert = ErrorMessage.forAlert(error);
            });
        };
    }
])

.controller('MotionPollSubmitCtrl', [
    '$scope',
    '$stateParams',
    '$http',
    'MotionPoll',
    'MotionPollBallot',
    'operator',
    'ErrorMessage',
    function ($scope, $stateParams, $http, MotionPoll, MotionPollBallot,
        operator, ErrorMessage) {
        var pollId = $stateParams.id;
        $scope.motionPoll = MotionPoll.get(pollId);
        $scope.alert = {};

        $scope.$watch(function () {
            return MotionPollBallot.lastModified();
        }, function () {
            $scope.mpb = _.find(MotionPollBallot.getAll(), function (mpb) {
                return mpb.delegate_id === operator.user.id &&
                    pollId === mpb.poll_id;
            });
        });

        $scope.vote = function (vote) {
            $scope.alert = {};
            vote = {
                value: vote,
            };
            $http.post('/votingcontroller/vote/' + pollId + '/', vote).then(null, function (error) {
                $scope.alert = ErrorMessage.forAlert(error);
            });
        };
    }
])

.controller('AssignmentPollSubmitCtrl', [
    '$scope',
    '$stateParams',
    '$http',
    'AssignmentPoll',
    'AssignmentPollBallot',
    'operator',
    'User',
    'gettextCatalog',
    'ErrorMessage',
    function ($scope, $stateParams, $http, AssignmentPoll, AssignmentPollBallot,
        operator, User, gettextCatalog, ErrorMessage) {
        var pollId = $stateParams.id;
        $scope.poll = AssignmentPoll.get(pollId);
        $scope.alert = {};

        // prepare the votes model
        $scope.votes = {};
        if ($scope.poll.pollmethod === 'votes') {
            $scope.votes.candidateIndex = -1;
        } else {
            _.forEach($scope.poll.options, function (option) {
                $scope.votes[option.candidate.id] = 'N';
            });
        }

        $scope.$watch(function () {
            return AssignmentPollBallot.lastModified();
        }, function () {
            $scope.apb = _.find(AssignmentPollBallot.getAll(), function (apb) {
                return apb.delegate_id === operator.user.id &&
                    pollId === apb.poll_id;
            });
        });

        $scope.getUserVotedFor = function () {
            return User.get(parseInt($scope.apb.vote)).full_name;
        };

        $scope.vote = function () {
            $scope.alert = {};
            var vote = {};
            var route;
            if ($scope.poll.pollmethod === 'votes') {
                route = 'candidate';
                vote.value = $scope.votes.candidateIndex;
                if (vote.value <= 0 || vote.value > $scope.poll.options.length) {
                    $scope.alert = {
                        msg: gettextCatalog.getString('Please select a candidate'),
                        type: 'danger',
                        show: true,
                    };
                    return;
                }
            } else {
                route = 'vote';
                vote.value = $scope.votes;
            }
            $http.post('/votingcontroller/' + route + '/' + pollId + '/', vote).then(
                null, function (error) {
                    $scope.alert = ErrorMessage.forAlert(error);
                }
            );
        };
    }
])

.controller('AssignmentPollVoteDetailCtrl', [
    '$scope',
    '$http',
    '$stateParams',
    'Assignment',
    'AssignmentPoll',
    'AssignmentPollBallot',
    function ($scope, $http, $stateParams, Assignment, AssignmentPoll, AssignmentPollBallot) {
        var pollId = $stateParams.id;
        var assignment = AssignmentPoll.get(pollId).assignment;
        Assignment.bindOne(assignment.id, $scope, 'assignment');
        AssignmentPoll.bindOne(pollId, $scope, 'poll');
        AssignmentPollBallot.bindAll({poll_id: pollId}, $scope, 'ballots');

        $scope.anonymizeVotes = function () {
            throw "TODO, ist das noch notwendig?";
            return $http.post(
                '/rest/openslides_votecollector/assignment-poll-keypad-connection/anonymize_votes/',
                {poll_id: $scope.poll.id}
            ).then(function (success) {}, function (error) {});
        };
    }
])

// Mark config strings for translation in javascript
.config([
    'gettext',
    function (gettext) {
        // Config strings
        gettext('Electronic Voting');
        gettext('Delegate board');
        gettext('VotingController URL');
        gettext('Example: http://localhost:8030');
        gettext('Please vote now!');
        gettext('Voting start prompt (projector overlay message)');
        gettext('Use countdown timer');
        gettext('Auto-start and stop a countdown timer when voting starts and stops.');
        gettext('Show delegate board');
        gettext('Show incoming votes on a delegate board on the projector.');
        gettext('Delegate board columns');
        gettext('Delegate name format used for delegate table cells');
        gettext('Short name. Example: Smi,J');
        gettext('Last name. Example: Smith');
        gettext('Full name. Example: Smith John');
        gettext('Vote anonymously');
        gettext('Keep individual voting behaviour secret on delegate board by using a single colour.');

        // Template hook strings.
        gettext('Start voting');
        gettext('Stop voting');
        gettext('Start election');
        gettext('Stop election');
        gettext('Start speakers voting');
        gettext('Stop speakers voting');
        gettext('Recount votes');
        gettext('Single votes');
        gettext('Voting result');
        gettext('Project vote result');
        gettext('Election result');
        gettext('Project election result');
        gettext('Clear votes');

        // Permission strings
        gettext('Can manage voting');
    }
]);

}());
