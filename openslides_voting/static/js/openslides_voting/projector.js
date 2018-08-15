(function () {

'use strict';

angular.module('OpenSlidesApp.openslides_voting.projector', [
    'OpenSlidesApp.openslides_voting'
])

.config([
    'slidesProvider',
    function(slidesProvider) {
        slidesProvider.registerSlide('voting/prompt', {
            template: 'static/templates/openslides_voting/slide_prompt.html'
        });
        slidesProvider.registerSlide('voting/icon', {
            template: 'static/templates/openslides_voting/slide_icon.html'
        });
        slidesProvider.registerSlide('voting/motion-poll', {
            template: 'static/templates/openslides_voting/slide_motion_poll.html',
        });
        slidesProvider.registerSlide('voting/assignment-poll', {
            template: 'static/templates/openslides_voting/slide_assignment_poll.html',
        });
    }
])

.controller('SlidePromptCtrl', [
    '$scope',
    function($scope) {
        // Attention! Each object that is used here has to be dealt with on server side.
        // Add it to the corresponding get_requirements method of the ProjectorElement
        // class.
        $scope.message = $scope.element.message;
    }
])

.controller('SlideIconCtrl', [
    '$scope',
    function($scope) {
        // Attention! Each object that is used here has to be dealt with on server side.
        // Add it to the corresponding get_requirements method of the ProjectorElement
        // class.
        $scope.message = $scope.element.message;
        $scope.visible = $scope.element.visible;
    }
])

.controller('SlideMotionPollCtrl', [
    '$scope',
    '$timeout',
    'AuthorizedVoters',
    'Config',
    'Motion',
    'MotionPoll',
    'MotionPollBallot',
    'User',
    'Delegate',
    'VotingController',
    function ($scope, $timeout, AuthorizedVoters, Config, Motion, MotionPoll,
              MotionPollBallot, User, Delegate, VotingController) {
        // Each DS resource used here must be yielded on server side in ProjectElement.get_requirements!
        var pollId = $scope.element.id,
            draw = false; // prevents redundant drawing

        $scope.$watch(function () {
            // MotionPoll watch implies Motion watch! So there is no need for an extra Motion watcher.
            return MotionPoll.lastModified(pollId);
        }, function () {
            $scope.poll = MotionPoll.get(pollId);
            if ($scope.poll !== undefined) {
                $scope.motion = Motion.get($scope.poll.motion_id);
            }
        });

        $scope.$watch(function () {
            return VotingController.lastModified(1) +
                AuthorizedVoters.lastModified(1) +
                Config.lastModified();
        }, function () {
            // Using timeout seems to give the browser more time to update the DOM.
            draw = true;
            $timeout(drawDelegateBoard, 0);
        });

        var drawDelegateBoard = function () {
            if (!draw) {
                return;
            }
            if (!Config.get('voting_show_delegate_board').value || !$scope.poll ||
                !$scope.motion) {
                // Only show the delegate board if the poll is published.
                $scope.delegateBoardHtml = '';
                draw = false;
                return;
            }

            // Get authorized voters.
            var voters = AuthorizedVoters.get(1).authorized_voters;
            if (_.keys(voters).length > 0) {
                // Create delegate board table.
                // console.log("Draw delegate board. Votes: " + MotionPollBallot.filter({poll_id: pollId}).length);
                var colCount = Config.get('voting_delegate_board_columns').value,
                    anonymous = Config.get('voting_anonymous').value,
                    table = '<table>',
                    i = 0;

                _.forEach(voters, function (delegates, voterId) {
                    _.forEach(delegates, function (id) {
                        var user = User.get(id),
                            mpb = MotionPollBallot.filter({poll_id: pollId, delegate_id: id});
                        var cls = '';
                        if (mpb.length === 1) {
                            // Set td class based on vote.
                            cls = anonymous ? 'seat-anonymous' : 'seat-' + mpb[0].vote;
                        }
                        if (i % colCount === 0) {
                            table += '<tr>';
                        }
                        // Cell label is keypad number + user name.
                        var keypad = Delegate.getKeypad(voterId);
                        var label = Delegate.getCellName(user);
                        if (keypad) {
                            label = Delegate.getKeypad(voterId).number + '<br/>' + label;
                        }
                        table += '<td class="seat ' + cls + '" ' +
                            'style="width: calc(100%/' + colCount + ');">' +
                            label + '</td>';
                        i++;
                    });
                });
                $scope.delegateBoardHtml = table;
            }
            else {
                // Clear delegate table.
                $scope.delegateBoardHtml = '';
            }
            draw = false;
        };
    }
])

.controller('SlideAssignmentPollCtrl', [
    '$scope',
    '$timeout',
    'AuthorizedVoters',
    'Config',
    'Assignment',
    'AssignmentPoll',
    'AssignmentPollBallot',
    'AssignmentPollType',
    'User',
    'Delegate',
    'VotingController',
    function ($scope, $timeout, AuthorizedVoters, Config, Assignment, AssignmentPoll,
              AssignmentPollBallot, AssignmentPollType, User, Delegate, VotingController) {
        // Each DS resource used here must be yielded on server side in ProjectElement.get_requirements!
        var pollId = $scope.element.id,
            draw = false; // prevents redundant drawing

        $scope.$watch(function () {
            // AssignmentPoll watch implies Assignment watch! So there is no need for an extra Assignment watcher.
            return AssignmentPoll.lastModified(pollId);
        }, function () {
            $scope.poll = AssignmentPoll.get(pollId);
            if ($scope.poll !== undefined) {
                $scope.assignment = Assignment.get($scope.poll.assignment_id);
                $scope.ynaVotes = $scope.poll.options[0].getVotes();
            }

            // Get poll type for assignment.
            var pollTypes = AssignmentPollType.filter({poll_id: pollId});
            var pollType = pollTypes.length >= 1 ? pollTypes[0].type : 'analog';
            $scope.showKey = pollType === 'votecollector' || pollType === 'votecollector_anonymous';

            draw = true;
            $timeout(drawDelegateBoard, 0);
        });

        $scope.$watch(function () {
            return VotingController.lastModified(1) +
                AuthorizedVoters.lastModified(1) +
                Config.lastModified();
        }, function () {
            // Using timeout seems to give the browser more time to update the DOM.
            draw = true;
            $timeout(drawDelegateBoard, 0);
        });

        var drawDelegateBoard = function () {
            if (!draw) {
                return;
            }
            if (!Config.get('voting_show_delegate_board').value || !$scope.poll ||
                !$scope.assignment) {
                // Only show the delegate board if the poll is published.
                $scope.delegateBoardHtml = '';
                draw = false;
                return;
            }

            // Get authorized voters.
            var voters = AuthorizedVoters.get(1).authorized_voters;
            if (_.keys(voters).length > 0) {
                // Create delegate board table.
                // console.log("Draw delegate board. Votes: " + AssignmentPollBallot.filter({poll_id: pollId}).length);
                var colCount = Config.get('voting_delegate_board_columns').value,
                    anonymous = Config.get('voting_anonymous').value,
                    table = '<table>',
                    i = 0;

                _.forEach(voters, function (delegates, voterId) {
                    _.forEach(delegates, function (id) {
                        var user = User.get(id),
                            apb = AssignmentPollBallot.filter({poll_id: pollId, delegate_id: id});
                        var cls = '';
                        if (apb.length > 0) {
                            apb = apb[0];
                            // Set td class based on vote.
                            if (anonymous) {
                                cls = 'seat-anonymous';
                            } else if ($scope.poll.pollmethod === 'votes') {
                                switch (apb.vote) {
                                    // global no and abstain
                                    case 'N':
                                        cls = 'seat-N'; break;
                                    case 'A':
                                        cls = 'seat-A'; break;
                                    default:
                                        cls = 'seat-voted'; break;
                                }
                            } else { // YNA and YN
                                if ($scope.poll.options.length === 1) {
                                    cls = 'seat-' + apb.vote[$scope.poll.options[0].candidate_id];
                                } else {
                                    cls = 'seat-voted';
                                }
                            }
                        }
                        if (i % colCount === 0) {
                            table += '<tr>';
                        }
                        // Cell label is keypad number + user name.
                        var keypad = Delegate.getKeypad(voterId);
                        var label = Delegate.getCellName(user);
                        if (keypad) {
                            label = Delegate.getKeypad(voterId).number + '<br/>' + label;
                        }
                        table += '<td class="seat ' + cls + '" ' +
                            'style="width: calc(100%/' + colCount + ');">' +
                            label + '</td>';
                        i++;
                    });
                });
                $scope.delegateBoardHtml = table;
            }
            else {
                // Clear delegate table.
                $scope.delegateBoardHtml = '';
            }
            draw = false;
        };
    }])

}());
