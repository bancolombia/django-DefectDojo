# Standard library imports
import logging
import re

# Third party imports
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from dojo.authorization.authorization import user_has_permission_or_403
from dojo.authorization.roles_permissions import Permissions

# Local application/library imports
from dojo.forms import DeleteNoteForm, NoteForm, TypedNoteForm
from dojo.models import Cred_User, Engagement, FileUpload, Finding, Note_Type, NoteHistory, Notes, Test

logger = logging.getLogger(__name__)

ATTACHED_FILE_RE = re.compile(r"\[Attached File: (?P<title>[^\]]+)\]")
PAGE_TO_FILE_ACCESS_TYPE = {
    "engagement": "Engagement",
    "test": "Test",
    "finding": "Finding",
}


def get_note_attachment_titles(entry):
    return ATTACHED_FILE_RE.findall(entry or "")


def strip_note_attachment_references(entry):
    stripped_entry = ATTACHED_FILE_RE.sub("", entry or "")
    return stripped_entry.rstrip()


def build_note_entry(entry, attached_files):
    clean_entry = strip_note_attachment_references(entry)
    attachment_references = "".join(
        f"\n\n[Attached File: {attached_file.title}]"
        for attached_file in attached_files
    )
    return f"{clean_entry}{attachment_references}" if attachment_references else clean_entry


def get_note_attached_files(note, obj):
    if not hasattr(obj, "files"):
        return []

    attached_file_titles = get_note_attachment_titles(note.entry)
    if not attached_file_titles:
        return []

    attached_files_by_title = {
        attached_file.title: attached_file
        for attached_file in obj.files.filter(title__in=attached_file_titles)
    }
    return [
        attached_files_by_title[attached_file_title]
        for attached_file_title in attached_file_titles
        if attached_file_title in attached_files_by_title
    ]


def get_note_attachment_parents(note):
    attachment_parents = []
    for related_manager_name in ("engagement_set", "test_set", "finding_set"):
        related_manager = getattr(note, related_manager_name, None)
        if related_manager is not None:
            attachment_parents.extend(list(related_manager.all()))
    return attachment_parents


def delete_orphaned_file(attached_file):
    if attached_file.finding_set.exists() or attached_file.test_set.exists() or attached_file.engagement_set.exists():
        return
    attached_file.delete()


def remove_files_from_note_parents(note, attached_files):
    attachment_parents = get_note_attachment_parents(note)
    for attached_file in attached_files:
        for attachment_parent in attachment_parents:
            if hasattr(attachment_parent, "files"):
                attachment_parent.files.remove(attached_file)
        delete_orphaned_file(attached_file)


def add_file_to_note_parents(note, attached_file):
    for attachment_parent in get_note_attachment_parents(note):
        if hasattr(attachment_parent, "files"):
            attachment_parent.files.add(attached_file)


def delete_note(request, note_id, page, objid):
    note = get_object_or_404(Notes, id=note_id)
    reverse_url = None
    object_id = None
    attached_files = []

    if page == "engagement":
        obj = get_object_or_404(Engagement, id=objid)
        object_id = obj.id
        reverse_url = "view_engagement"
    elif page == "test":
        obj = get_object_or_404(Test, id=objid)
        object_id = obj.id
        reverse_url = "view_test"
    elif page == "finding":
        obj = get_object_or_404(Finding, id=objid)
        object_id = obj.id
        reverse_url = "view_finding"
    elif page == "cred":
        obj = get_object_or_404(Cred_User, id=objid)
        object_id = obj.id
        reverse_url = "view_cred_details"

    if hasattr(obj, "files"):
        attached_files = get_note_attached_files(note, obj)

    form = DeleteNoteForm(request.POST, instance=note)

    if page is None:
        raise PermissionDenied
    if str(request.user) != note.author.username:
        user_has_permission_or_403(request.user, obj, Permissions.Note_Delete)

    if form.is_valid():
        remove_files_from_note_parents(note, attached_files)
        note.delete()
        messages.add_message(request,
                             messages.SUCCESS,
                             _("Note deleted."),
                             extra_tags="alert-success")
    else:
        messages.add_message(request,
                             messages.SUCCESS,
                             _("Note was not successfully deleted."),
                             extra_tags="alert-danger")

    return HttpResponseRedirect(reverse(reverse_url, args=(object_id, )))


def edit_note(request, note_id, page, objid):
    note = get_object_or_404(Notes, id=note_id)
    reverse_url = None
    object_id = None

    if page is None:
        raise PermissionDenied

    if page == "engagement":
        obj = get_object_or_404(Engagement, id=objid)
        object_id = obj.id
        reverse_url = "view_engagement"
    elif page == "test":
        obj = get_object_or_404(Test, id=objid)
        object_id = obj.id
        reverse_url = "view_test"
    elif page == "finding":
        obj = get_object_or_404(Finding, id=objid)
        object_id = obj.id
        reverse_url = "view_finding"

    if str(request.user) != note.author.username:
        user_has_permission_or_403(request.user, obj, Permissions.Note_Edit)

    existing_attached_files = get_note_attached_files(note, obj) if page == "finding" else []
    selected_removed_file_ids = request.POST.getlist("remove_evidence_files") if request.method == "POST" else []

    note_type_activation = Note_Type.objects.filter(is_active=True).count()
    if note_type_activation:
        available_note_types = find_available_notetypes(obj, note)

    if request.method == "POST":
        if note_type_activation:
            form = TypedNoteForm(request.POST, request.FILES, available_note_types=available_note_types, instance=note, show_evidence_upload=page == "finding")
        else:
            form = NoteForm(request.POST, request.FILES, instance=note, show_evidence_upload=page == "finding")
        if form.is_valid():
            removed_file_ids = {
                int(file_id)
                for file_id in request.POST.getlist("remove_evidence_files")
                if file_id.isdigit()
            }
            removed_attached_files = [attached_file for attached_file in existing_attached_files if attached_file.id in removed_file_ids]
            retained_attached_files = [attached_file for attached_file in existing_attached_files if attached_file.id not in removed_file_ids]

            note = form.save(commit=False)
            note.edited = True
            note.editor = request.user
            note.edit_time = timezone.now()
            note.entry = strip_note_attachment_references(note.entry)
            
            # Process uploaded file if provided and it's a Finding
            edit_evidence_file = form.cleaned_data.get('edit_evidence_file')
            if edit_evidence_file and page == "finding":
                uploaded_file = FileUpload.objects.create(
                    title=f"Review Proof - {timezone.now().strftime('%Y%m%d_%H%M%S')}",
                    file=edit_evidence_file
                )
                retained_attached_files.append(uploaded_file)
                add_file_to_note_parents(note, uploaded_file)

            note.entry = build_note_entry(note.entry, retained_attached_files)
            if note_type_activation:
                history = NoteHistory(note_type=note.note_type,
                                      data=note.entry,
                                      time=note.edit_time,
                                      current_editor=note.editor)
            else:
                history = NoteHistory(data=note.entry,
                                      time=note.edit_time,
                                      current_editor=note.editor)
            history.save()
            note.history.add(history)
            note.save()
            remove_files_from_note_parents(note, removed_attached_files)
            
            obj.last_reviewed = note.date
            obj.last_reviewed_by = request.user
            obj.save()
            form = NoteForm()
            messages.add_message(request,
                                messages.SUCCESS,
                                _("Note edited."),
                                extra_tags="alert-success")
            return HttpResponseRedirect(reverse(reverse_url, args=(object_id, )))
        messages.add_message(request,
                            messages.SUCCESS,
                            _("Note was not succesfully edited."),
                            extra_tags="alert-danger")
    elif note_type_activation:
        form = TypedNoteForm(available_note_types=available_note_types, instance=note, show_evidence_upload=page == "finding", initial={"entry": strip_note_attachment_references(note.entry)})
    else:
        form = NoteForm(instance=note, show_evidence_upload=page == "finding", initial={"entry": strip_note_attachment_references(note.entry)})

    return render(
        request, "dojo/edit_note.html", {
            "note": note,
            "form": form,
            "existing_attached_files": existing_attached_files,
            "selected_removed_file_ids": selected_removed_file_ids,
            "file_access_obj_type": PAGE_TO_FILE_ACCESS_TYPE.get(page),
            "page": page,
            "objid": objid,
        })


def note_history(request, note_id, page, objid):
    note = get_object_or_404(Notes, id=note_id)
    reverse_url = None
    object_id = None

    if page == "engagement":
        obj = get_object_or_404(Engagement, id=objid)
        object_id = obj.id
        reverse_url = "view_engagement"
    elif page == "test":
        obj = get_object_or_404(Test, id=objid)
        object_id = obj.id
        reverse_url = "view_test"
    elif page == "finding":
        obj = get_object_or_404(Finding, id=objid)
        object_id = obj.id
        reverse_url = "view_finding"

    if page is None:
        raise PermissionDenied
    if str(request.user) != note.author.username:
        user_has_permission_or_403(request.user, obj, Permissions.Note_View_History)

    history = note.history.all()

    if request.method == "POST":
        return HttpResponseRedirect(reverse(reverse_url, args=(object_id, )))

    return render(
        request, "dojo/view_note_history.html", {
            "history": history,
            "note": note,
            "page": page,
            "objid": objid,
        })


def find_available_notetypes(finding, editing_note):
    notes = finding.notes.all()
    single_note_types = Note_Type.objects.filter(is_single=True, is_active=True).values_list("id", flat=True)
    multiple_note_types = Note_Type.objects.filter(is_single=False, is_active=True).values_list("id", flat=True)
    available_note_types = []
    for note_type_id in multiple_note_types:
        available_note_types.append(note_type_id)
    for note_type_id in single_note_types:
        for note in notes:
            if note_type_id == note.note_type_id:
                break
        else:
            available_note_types.append(note_type_id)
    available_note_types.append(editing_note.note_type_id)
    available_note_types = list(set(available_note_types))
    return Note_Type.objects.filter(id__in=available_note_types).order_by("-id")
