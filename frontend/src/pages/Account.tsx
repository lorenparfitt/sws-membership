import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import { api, ApiError, type Profile, type ProfileBody } from "../api";
import { useAuth } from "../auth";

const EMPTY: ProfileBody = {
  first_name: "",
  last_name: "",
  phone: "",
  date_of_birth: null,
  address_line_1: "",
  address_line_2: "",
  city: "",
  province: "BC",
  postal_code: "",
  sports: [],
};

function toBody(profile: Profile): ProfileBody {
  return {
    first_name: profile.first_name,
    last_name: profile.last_name,
    phone: profile.phone ?? "",
    date_of_birth: profile.date_of_birth,
    address_line_1: profile.address_line_1 ?? "",
    address_line_2: profile.address_line_2 ?? "",
    city: profile.city ?? "",
    province: profile.province ?? "BC",
    postal_code: profile.postal_code ?? "",
    sports: profile.sports,
  };
}

export function Account() {
  const { me, refresh } = useAuth();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [form, setForm] = useState<ProfileBody>(EMPTY);
  const [sports, setSports] = useState<{ value: string; label: string }[]>([]);
  const [photoVersion, setPhotoVersion] = useState(0);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [passwordNote, setPasswordNote] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    api.profile().then((p) => {
      setProfile(p);
      setForm(toBody(p));
    });
    api.sports().then(setSports);
  }, []);

  function field(name: keyof ProfileBody) {
    return (event: ChangeEvent<HTMLInputElement>) => setForm({ ...form, [name]: event.target.value });
  }

  function toggleSport(value: string) {
    setForm({
      ...form,
      sports: form.sports.includes(value) ? form.sports.filter((s) => s !== value) : [...form.sports, value],
    });
  }

  async function saveProfile(event: FormEvent) {
    event.preventDefault();
    setNote(null);
    try {
      const saved = await api.updateProfile({ ...form, date_of_birth: form.date_of_birth || null });
      setProfile(saved);
      setForm(toBody(saved));
      await refresh();
      setNote({ ok: true, text: "Profile saved." });
    } catch (error) {
      setNote({ ok: false, text: error instanceof ApiError ? String(error.detail) : "Could not save." });
    }
  }

  async function choosePhoto(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setNote(null);
    try {
      const saved = await api.uploadMyPhoto(file);
      setProfile(saved);
      setPhotoVersion((v) => v + 1);
      setNote({ ok: true, text: "Photo saved." });
    } catch (error) {
      setNote({ ok: false, text: error instanceof ApiError ? String(error.detail) : "Could not upload the photo." });
    }
  }

  async function savePassword(event: FormEvent) {
    event.preventDefault();
    setPasswordNote(null);
    if (password !== again) {
      setPasswordNote({ ok: false, text: "The two entries do not match." });
      return;
    }
    try {
      await api.setPassword(password);
      await refresh();
      setPassword("");
      setAgain("");
      setPasswordNote({ ok: true, text: "Password saved." });
    } catch (error) {
      setPasswordNote({
        ok: false,
        text: error instanceof ApiError && error.status === 400 ? "Passwords need at least 10 characters." : "Could not save the password.",
      });
    }
  }

  if (!me || !profile) return <p>Loading…</p>;

  return (
    <section className="account">
      <div className="card">
        <h2>Account</h2>
        <p>
          Member number <strong>{me.member_number}</strong>, {me.email}
        </p>
        {profile.missing.length > 0 ? (
          <p className="problem">
            To buy passes, complete your profile: {profile.missing.join(", ")}.
          </p>
        ) : (
          <p className="ok">Profile complete.</p>
        )}
      </div>

      <div className="card">
        <h3>Photo</h3>
        <p className="label">A clear photo of your face, for your member card and the gate.</p>
        <div className="photo-row">
          {profile.has_photo ? (
            <img className="photo" src={`/api/me/photo?v=${photoVersion}`} alt="Your member photo" />
          ) : (
            <div className="photo placeholder">No photo</div>
          )}
          <label className="file">
            {profile.has_photo ? "Replace photo" : "Add photo"}
            <input type="file" accept="image/*" capture="user" onChange={choosePhoto} />
          </label>
        </div>
      </div>

      <form className="card" onSubmit={saveProfile}>
        <h3>Details</h3>
        <div className="two">
          <label>
            First name
            <input required value={form.first_name} onChange={field("first_name")} />
          </label>
          <label>
            Last name
            <input required value={form.last_name} onChange={field("last_name")} />
          </label>
        </div>
        <div className="two">
          <label>
            Phone
            <input value={form.phone} onChange={field("phone")} />
          </label>
          <label>
            Date of birth
            <input
              type="date"
              required
              value={form.date_of_birth ?? ""}
              disabled={profile.date_of_birth !== null}
              onChange={(event) => setForm({ ...form, date_of_birth: event.target.value })}
            />
          </label>
        </div>
        {profile.date_of_birth !== null && (
          <p className="label">Date of birth is set. Ask staff if it needs correcting.</p>
        )}
        <label>
          Address
          <input required value={form.address_line_1} onChange={field("address_line_1")} />
        </label>
        <label>
          Address line 2
          <input value={form.address_line_2} onChange={field("address_line_2")} />
        </label>
        <div className="two">
          <label>
            City
            <input required value={form.city} onChange={field("city")} />
          </label>
          <label>
            Province
            <input required value={form.province} onChange={field("province")} />
          </label>
        </div>
        <label>
          Postal code
          <input required value={form.postal_code} onChange={field("postal_code")} />
        </label>
        <fieldset>
          <legend>What do you ride? Pick all that apply.</legend>
          {sports.map((sport) => (
            <label key={sport.value} className="checkbox">
              <input
                type="checkbox"
                checked={form.sports.includes(sport.value)}
                onChange={() => toggleSport(sport.value)}
              />
              {sport.label}
            </label>
          ))}
        </fieldset>
        <button type="submit">Save details</button>
        {note && <p className={note.ok ? "ok" : "problem"}>{note.text}</p>}
      </form>

      <form className="card" onSubmit={savePassword}>
        <h3>{me.has_password ? "Change password" : "Set a password"}</h3>
        <p className="label">At least 10 characters. The emailed sign-in link keeps working either way.</p>
        <label>
          New password
          <input type="password" required minLength={10} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        <label>
          New password again
          <input type="password" required autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} />
        </label>
        <button type="submit">Save password</button>
        {passwordNote && <p className={passwordNote.ok ? "ok" : "problem"}>{passwordNote.text}</p>}
      </form>
    </section>
  );
}
