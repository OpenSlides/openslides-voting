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
    }
])

.controller('SlidePromptCtrl', [
    '$scope',
    function($scope) {
        // Attention! Each object that is used here has to be dealt with on server side.
        // Add it to the corresponding get_requirements method of the ProjectorElement
        // class.
        $scope.message = $scope.element.message;
        $scope.visible = $scope.element.visible;
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
    '$http',
    'Config',
    'Motion',
    'MotionPoll',
    'MotionPollBallot',
    'User',
    'Delegate',
    'Keypad',
    'VotingPrinciple',
    'VotingProxy',
    'VotingShare',
    'VoteCollector',
    function ($scope, $timeout, $http, Config, Motion, MotionPoll, MotionPollBallot, User, Delegate,
              Keypad, VotingPrinciple, VotingProxy, VotingShare, VoteCollector) {
        // Each DS resource used here must be yielded on server side in ProjectElement.get_requirements!
        var pollId = $scope.element.id,
            motionId = 0;

        $scope.$watch(function () {
            // MotionPoll watch implies Motion watch! So there is no need to watch Motion.
            return MotionPoll.lastModified(pollId);
        }, function () {
            $scope.poll = MotionPoll.get(pollId);
            if ($scope.poll !== undefined) {
                $scope.motion = $scope.poll.motion;
                motionId = $scope.motion.id;
            }
            // TODO: $scope.precision = motion.category ? VotingPrinciple.getPrecision(motion.category.name) : 0;
        });

        var delegates = null;
        var drawDelegateBoard = function () {
            if (delegates === null) {
                console.log("Cannot draw delegate board. No delegates.");
                return;
            }

            // Create delegate board table.
            console.log("Draw delegate board. Votes: " + MotionPollBallot.filter({poll_id: pollId}).length);
            var colCount = Config.get('voting_delegate_board_columns').value;
            var anonymous = Config.get('voting_anonymous').value;
            var table = '<table>', i = 0;
            angular.forEach(delegates, function (value, key) {
                angular.forEach(value, function (id) {
                    var user = User.get(id),
                        mpbs = MotionPollBallot.filter({poll_id: pollId, delegate_id: id});
                    var cls = '';
                    if (mpbs.length == 1) {
                        // Set td class based on vote.
                        cls = anonymous ? 'seat-V' : 'seat-' + mpbs[0].vote;
                    }
                    if (i % colCount === 0) {
                        table += '<tr>';
                    }
                    // Cell label is key + user name.
                    var label = key + '<br/>' + Delegate.getCellName(user);
                    table += '<td class="seat ' + cls + '">' + label + '</td>';
                    i++;
                });
            });
            $scope.delegateBoardHtml = table;
        };

        var updatePromise;
        var updateDelegateBoard = function () {
            if (Config.get('voting_show_delegate_board').value) {
                // Get a list of delegates admitted to vote.
                var url = '/voting/admitted_delegates/';
                if ($scope.motion.category_id) {
                    url += $scope.motion.category_id + '/';
                }
                console.log("Update delegate board.");
                $http.get(url).then(
                    function (success) {
                        delegates = success.data.delegates;
                        drawDelegateBoard();
                    }
                );
            }
            else {
                $scope.delegateBoardHtml = '';
            }
        };

        $scope.$watch(function () {
            return VoteCollector.lastModified(1);
        }, function () {
            // Using timeout seems to give the browser more time to update the DOM.
            if (delegates === null) {
                $timeout(updateDelegateBoard, 0);
            }
            else {
                $timeout(drawDelegateBoard, 0);
            }
        });

        $scope.$watch(function () {
            // NOTE: Watch User, Keypad, VotingShare, VotingProxy to reflect registration changes.
            // TODO: Projector does not update if poll is deleted.
            return User.lastModified() +
                    Keypad.lastModified() +
                    Motion.lastModified(motionId) +
                    VotingProxy.lastModified() +
                    VotingShare.lastModified();
        }, function () {
            if ($scope.poll !== undefined && !$scope.poll.has_votes) {
                if (updatePromise) {
                    $timeout.cancel(updatePromise);
                }
                // Update delegate board to reflect registration changes.
                // NOTE: Delegates whose status has changed to attending or whose keypad number has changed
                // while voting IS ACTIVE cannot cast a vote! See rpc.get_keypads.
                updatePromise = $timeout(updateDelegateBoard, 100);
            }
        });

        $scope.$watch(function () {
            // Watch MotionPollBallot to update delegate board AFTER VoteCollector has been stopped.
            // This also handles "Clear votes".
            return MotionPollBallot.lastModified();
        }, function () {
            if (updatePromise) {
                $timeout.cancel(updatePromise);
            }
            // Schedule a final update.
            updatePromise = $timeout(drawDelegateBoard, 1000);
        });

        $scope.$on('$destroy', function () {
            $timeout.cancel(updatePromise);
        });
    }
])

}());
