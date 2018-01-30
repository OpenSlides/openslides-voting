(function () {

'use strict';

angular.module('OpenSlidesApp.openslides_voting.voting', [
    'OpenSlidesApp.openslides_voting'
])

.controller('VotingCtrl', [
    '$scope',
    '$http',
    'gettextCatalog',
    'MotionPollBallot',
    'Projector',
    'VoteCollector',
    function ($scope, $http, gettextCatalog, MotionPollBallot, Projector, VoteCollector) {
        VoteCollector.bindOne(1, $scope, 'vc');

        var clearForm = function () {
            $scope.poll.yes = null;
            $scope.poll.no = null;
            $scope.poll.abstain = null;
            $scope.poll.votesvalid = null;
            $scope.poll.votesinvalid = null;
            $scope.poll.votescast = null;
        };

        $scope.canStartVoting = function () {
            return $scope.poll.votescast === null &&
                (!$scope.vc.is_voting || $scope.vc.voting_mode == 'Item' || $scope.vc.voting_mode == 'Test');
        };

        $scope.canStopVoting = function () {
            return $scope.vc.is_voting && $scope.vc.voting_mode == 'MotionPoll' &&
                $scope.vc.voting_target == $scope.poll.id;
        };

        $scope.canClearVotes = function () {
            return !$scope.vc.is_voting && $scope.poll.votescast !== null;
        };

        $scope.startVoting = function () {
            $scope.$parent.$parent.$parent.alert = {};

            // Start votecollector.
            $http.get('/votecollector/start_voting/' + $scope.poll.id + '/').then(
                function (success) {
                    if (success.data.error) {
                        $scope.$parent.$parent.$parent.alert = { type: 'danger', msg: success.data.error, show: true };
                    }
                },
                function (failure) {
                    $scope.$parent.$parent.$parent.alert = {
                        type: 'danger',
                        msg: $scope.vc.getErrorMessage(failure.status, failure.statusText),
                        show: true };
                }
            );
        };

        $scope.stopVoting = function () {
            $scope.$parent.$parent.$parent.alert = {};

            // Stop votecollector.
            $http.get('/votecollector/stop/').then(
                function (success) {
                    if (success.data.error) {
                        $scope.$parent.$parent.$parent.alert = { type: 'danger',
                            msg: success.data.error, show: true };
                    }
                    else {
                        $http.get('/votecollector/result_voting/' + $scope.poll.id + '/').then(
                            function (success) {
                                if (success.data.error) {
                                    $scope.$parent.$parent.$parent.alert = { type: 'danger',
                                        msg: success.data.error, show: true };
                                }
                                else {
                                    // Store result in DS model; updates form inputs.
                                    $scope.poll.yes = success.data.votes[0];
                                    $scope.poll.no = success.data.votes[1];
                                    $scope.poll.abstain = success.data.votes[2];
                                    $scope.poll.votesvalid = $scope.poll.yes + $scope.poll.no + $scope.poll.abstain;
                                    $scope.poll.votesinvalid = 0;
                                    $scope.poll.votescast = $scope.poll.votesvalid;

                                    // Prompt user to save result.
                                    $scope.$parent.$parent.$parent.alert = {
                                        type: 'info',
                                        msg: gettextCatalog.getString('Motion voting has finished.') + ' ' +
                                             // gettextCatalog.getString('Received votes:') + ' ' +
                                             // $scope.votes_received + ' / ' + $scope.vc.voters_count + '. ' +
                                             gettextCatalog.getString('Save this result now!'),
                                        show: true
                                    };
                                }
                            }
                        );
                    }
                },
                function (failure) {
                    $scope.$parent.$parent.$parent.alert = {
                        type: 'danger',
                        msg: $scope.vc.getErrorMessage(failure.status, failure.statusText),
                        show: true };
                }
            );
        };

        $scope.clearVotes = function () {
            $scope.$parent.$parent.$parent.alert = {};
            $http.get('/votecollector/clear_voting/' + $scope.poll.id + '/').then(
                function (success) {
                    clearForm();
                }
            );
        };

        $scope.getVotingStatus = function () {
            if ($scope.vc !== undefined) {
                if ($scope.vc.is_voting && $scope.vc.voting_mode == 'Test') {
                    return gettextCatalog.getString('System test is running.');
                }
                if ($scope.vc.is_voting && $scope.vc.voting_mode == 'Item') {
                    return gettextCatalog.getString('Speakers voting is running for agenda item') + ' ' +
                        $scope.vc.voting_target + '.';
                }
                if ($scope.vc.is_voting && $scope.vc.voting_mode == 'AssignmentPoll') {
                    return gettextCatalog.getString('An election is running.');
                }
                if ($scope.vc.is_voting && $scope.vc.voting_mode == 'MotionPoll') {
                    if ($scope.vc.voting_target != $scope.poll.id) {
                        return gettextCatalog.getString('Another motion voting is running.');
                    }
                    // NOTE: Must not use $scope.vc.votes_received. If server uses multiple workers
                    // VoteCollector auto-updates may come in out of order.
                    $scope.votes_received = MotionPollBallot.filter({poll_id: $scope.poll.id}).length;
                    return gettextCatalog.getString('Votes received:') + ' ' +
                        // TODO: Add voting duration.
                        $scope.votes_received + ' / ' + $scope.vc.voters_count;
                }
            }
            return '';
        };

        $scope.projectSlide = function () {
            return $http.post(
                '/rest/core/projector/1/prune_elements/',
                [{name: 'voting/motion-poll', id: $scope.poll.id}]
            );
        };

        $scope.isProjected = function () {
            // Returns true if there is a projector element with the same
            // name and the same id of $scope.poll.
            var projector = Projector.get(1);
            var isProjected;
            if (typeof projector !== 'undefined') {
                var self = this;
                var predicate = function (element) {
                    return element.name == "voting/motion-poll" &&
                        typeof element.id !== 'undefined' &&
                        element.id == $scope.poll.id;
                };
                isProjected = typeof _.findKey(projector.elements, predicate) === 'string';
            } else {
                isProjected = false;
            }
            return isProjected;
        }
    }
])

.controller('SpeakerListCtrl', [
    '$scope',
    '$http',
    'VoteCollector',
    function ($scope, $http, VoteCollector) {
        VoteCollector.bindOne(1, $scope, 'vc');

        $scope.canStartVoting = function () {
            return (!$scope.vc.is_voting ||
                    ($scope.vc.voting_mode == 'Item' && $scope.vc.voting_target != $scope.item.id) ||
                    $scope.vc.voting_mode == 'Test');
        };

        $scope.canStopVoting = function () {
            return $scope.vc.is_voting && $scope.vc.voting_mode == 'Item' &&
                $scope.vc.voting_target == $scope.item.id;
        };

        $scope.startVoting = function () {
            $scope.vcAlert = {};
            $http.get('/votecollector/start_speaker_list/' + $scope.item.id + '/').then(
                function (success) {
                    if (success.data.error) {
                        $scope.vcAlert = { type: 'danger', msg: success.data.error, show: true };
                    }
                },
                function (failure) {
                    $scope.vcAlert = {
                        type: 'danger',
                        msg: $scope.vc.getErrorMessage(failure.status, failure.statusText),
                        show: true };
                }
            );
        };

        $scope.stopVoting = function () {
            $scope.vcAlert = {};
            $http.get('/votecollector/stop/').then(
                function (success) {
                    if (success.data.error) {
                        $scope.vcAlert = { type: 'danger', msg: success.data.error, show: true };
                    }
                },
                function (failure) {
                    $scope.vcAlert = {
                        type: 'danger',
                        msg: $scope.vc.getErrorMessage(failure.status, failure.statusText),
                        show: true };
                }
            );
        };
    }
])

.controller('VoteCountCtrl', [
    '$scope',
    '$http',
    function ($scope, $http) {
        // Recalculate vote result.
        $scope.countVotes = function () {
            $http.post('/voting/count/' + $scope.poll.id + '/');
        };
    }
])

// Template hook motionPollFormButtons
.run([
    'templateHooks',
    function (templateHooks) {
        templateHooks.registerHook({
            Id: 'motionPollFormButtons',
            template:
                '<div ng-controller="VotingCtrl" ng-init="poll=$parent.$parent.model" class="spacer">' +
                    '<button type="button"' +
                        'ng-if="canStartVoting()" ng-click="startVoting()"' +
                        'class="btn btn-default">' +
                        '<i class="fa fa-wifi" aria-hidden="true"></i> ' +
                        '{{ \'Start voting\' | translate }}</button> ' +
                    '<button type="button"' +
                        'ng-if="canStopVoting()" ng-click="stopVoting()"' +
                        'class="btn btn-primary">' +
                        '<i class="fa fa-wifi" aria-hidden="true"></i> '+
                        '{{ \'Stop voting\' | translate }}</button> ' +
                    '<button type="button"' +
                        'ng-if="canClearVotes()" ng-click="clearVotes()"' +
                        'class="btn btn-default">' +
                        '<i class="fa fa-trash" aria-hidden="true"></i> '+
                        '{{ \'Clear votes\' | translate }}</button> ' +
                    '<button type="button" os-perms="core.can_manage_projector"' +
                        'ng-class="{ \'btn-primary\': isProjected() }"' +
                        'ng-click="projectSlide()"' +
                        'class="btn btn-default"' +
                        'title="{{ \'Project vote result\' | translate }}">' +
                        '<i class="fa fa-video-camera"></i> ' +
                        '{{ \'Voting result\' | translate }}</button>' +
                    '<p>{{ getVotingStatus() }}</p>' +
                '</div>'
        })
    }
])

// Template hook motionPollSmallButtons
.run([
    'templateHooks',
    function (templateHooks) {
        templateHooks.registerHook({
            Id: 'motionPollSmallButtons',
            template:
                '<div ng-controller="VoteCountCtrl" ng-if="poll.has_votes" class="spacer">' +
                    '<button type="button" os-perms="openslides_voting.can_manage"'+
                        'ng-click="countVotes()" ' +
                        'class="btn btn-xs btn-default">' +
                        '<i class="fa fa-repeat" aria-hidden="true"></i> ' +
                        '{{ \'Recount votes\' | translate }}</button>' +
                '</div>' +
                '<div ng-if="poll.has_votes" class="spacer">' +
                    '<a ui-sref="openslides_voting.motionPoll.detail({id: poll.id})" role="button"' +
                        'os-perms="openslides_voting.can_manage"' +
                        'class="btn btn-xs btn-default">' +
                        '<i class="fa fa-table" aria-hidden="true"></i> ' +
                        '{{ \'Single votes\' | translate }}</a>' +
                '</div>'
        })
    }
])

// Template hook itemDetailListOfSpeakersButtons
.run([
    'gettextCatalog',
    'templateHooks',
    function (gettextCatalog, templateHooks) {
        templateHooks.registerHook({
            Id: 'itemDetailListOfSpeakersButtons',
            template:
                '<div ng-controller="SpeakerListCtrl" ng-init="item=$parent.$parent.item" class="spacer">' +
                    '<button ng-if="canStartVoting()"' +
                        'ng-click="startVoting()"' +
                        'class="btn btn-sm btn-default">' +
                        '<i class="fa fa-wifi" aria-hidden="true"></i>'+
                        '{{ \'Start speakers voting\' | translate }}</button> ' +
                    '<button ng-if="canStopVoting()"' +
                        'ng-click="stopVoting()"' +
                        'class="btn btn-sm btn-primary">' +
                        '<i class="fa fa-wifi" aria-hidden="true"></i> '+
                        '{{ \'Stop speakers voting\' | translate }}</button>' +
                    '<uib-alert ng-show="vcAlert.show" type="{{ vcAlert.type }}" ng-click="vcAlert={}" close="vcAlert={}">' +
                        '{{ vcAlert.msg }}</uib-alert>' +
                '</div>'
        })
    }
])

// Mark config strings for translation in javascript
.config([
    'gettext',
    function (gettext) {
        // Config strings
        gettext('Electronic Voting');
        gettext('Delegate board');
        gettext('VoteCollector URL');
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
])

}());
