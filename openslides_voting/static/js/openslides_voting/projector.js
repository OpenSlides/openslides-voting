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
    'AuthorizedVoters',
    'Config',
    'MotionPollBallot',
    'User',
    'Delegate',
    'VotingController',
    function ($scope, $timeout, $http, AuthorizedVoters, Config, MotionPollBallot, User, Delegate, VotingController) {
        // Each DS resource used here must be yielded on server side in ProjectElement.get_requirements!
        var pollId = $scope.element.id,
            draw = false; // prevents redundant drawing

        var drawDelegateBoard = function () {
            if (Config.get('voting_show_delegate_board').value) {
                if (!draw) return;

                // Get authorized voters.
                var voters = AuthorizedVoters.get(1).authorized_voters;
                if (Object.keys(voters).length > 0) {
                    // Create delegate board table.
                    console.log("Draw delegate board. Votes: " + MotionPollBallot.filter({poll_id: pollId}).length);
                    var colCount = Config.get('voting_delegate_board_columns').value,
                        anonymous = Config.get('voting_anonymous').value,
                        table = '<table>',
                        i = 0;

                    angular.forEach(voters, function (delegates, voterId) {
                        angular.forEach(delegates, function (id) {
                            var user = User.get(id),
                                mpbs = MotionPollBallot.filter({poll_id: pollId, delegate_id: id});
                            var cls = '';
                            if (mpbs.length === 1) {
                                // Set td class based on vote.
                                cls = anonymous ? 'seat-V' : 'seat-' + mpbs[0].vote;
                            }
                            if (i % colCount === 0) {
                                table += '<tr>';
                            }
                            // Cell label is keypad number + user name.
                            var label = Delegate.getKeypad(voterId).number + '<br/>' + Delegate.getCellName(user);
                            table += '<td class="seat ' + cls + '">' + label + '</td>';
                            i++;
                        });
                    });
                    $scope.delegateBoardHtml = table;
                }
                else {
                    // Clear delegate table.
                    console.log("Clear delegate table.");
                    $scope.delegateBoardHtml = '';
                }
                draw = false;
            }
            else {
                $scope.delegateBoardHtml = '';
            }
        };

        $scope.$watch(function () {
            return VotingController.lastModified(1);
        }, function () {
            // Using timeout seems to give the browser more time to update the DOM.
            console.log("VC modified.");
            draw = true;
            $timeout(drawDelegateBoard, 0);
        });

        $scope.$watch(function () {
            return AuthorizedVoters.lastModified(1);
        }, function () {
            console.log("AV modified.");
            draw = true;
            $timeout(drawDelegateBoard, 0);
        });
    }
]);

}());
